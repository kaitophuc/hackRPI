#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN RGB565 display. No dependencies; one producer owns the FPGA interface."""
from __future__ import print_function
import argparse
import base64
import binascii
import collections
import hashlib
import json
import os
import socket
import signal
import struct
import sys
import threading
import time
try:
    from urllib.parse import urlsplit, parse_qs
except ImportError:
    from urlparse import urlsplit, parse_qs
try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        pass

if sys.version_info[0] < 3:
    from legacy_host import Device, Snapshot, monotonic
else:
    from host import Device, Snapshot
    monotonic = time.monotonic

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_CONTROL = 4096


def websocket_packet(payload, opcode=2):
    size = len(payload)
    if size < 126:
        header = struct.pack("BB", 0x80 | opcode, size)
    elif size < 65536:
        header = struct.pack("BB", 0x80 | opcode, 126) + struct.pack("!H", size)
    else:
        header = struct.pack("BB", 0x80 | opcode, 127) + struct.pack("!Q", size)
    return header + payload


def read_exact(stream, size):
    data = []
    remaining = size
    while remaining:
        part = stream.read(remaining)
        if not part:
            raise EOFError("WebSocket disconnected")
        data.append(part)
        remaining -= len(part)
    return b"".join(data)


def receive_control(stream):
    first, second = struct.unpack("BB", read_exact(stream, 2))
    if first & 0x70 or not first & 0x80 or not second & 0x80:
        raise ValueError("fragmented/unmasked client message")
    opcode, size = first & 15, second & 127
    if size == 126:
        size = struct.unpack("!H", read_exact(stream, 2))[0]
    elif size == 127:
        size = struct.unpack("!Q", read_exact(stream, 8))[0]
    if size > MAX_CONTROL or (opcode >= 8 and size > 125):
        raise ValueError("control message too large")
    mask = bytearray(read_exact(stream, 4))
    payload = bytearray(read_exact(stream, size))
    return opcode, b"".join(struct.pack("B", value ^ mask[i % 4]) for i, value in enumerate(payload))


class FrameHub(object):
    """One immutable latest frame; no per-consumer frame queue."""
    def __init__(self, source, fps=15.0, encoder=None):
        self.source = source
        self.period = 1.0 / fps
        self.condition = threading.Condition()
        self.latest = None
        self.latest_metadata = {}
        self.generation = 0
        self.error = None
        self.running = True
        self.paused = False
        self.captured = 0
        self.started = monotonic()
        self.encoder = encoder
        self.latest_jpeg = None
        self.jpeg_generation = 0
        self.jpeg_error = None
        self.jpeg_encoded = 0
        self.jpeg_last_ack_ms = None
        self.displays = {}

    def display_ack(self, client, message, sent):
        now = monotonic()
        with self.condition:
            state = self.displays[client]
            state['times'].append(now)
            state['frames'] += 1
            state['sequence'] = message['sequence']
            state['send_ack_ms'] = (now-sent)*1000
            state['canvas_updated'] = message.get('canvas_updated') is True
            state['visible'] = message.get('visible') is True

    def encode_latest(self):
        """One independent encoder consumes latest snapshots, never FPGA RAM."""
        consumed = 0
        while self.running:
            with self.condition:
                while self.running and (self.latest is None or self.generation == consumed):
                    self.condition.wait(timeout=0.25)
                if not self.running:
                    break
                frame, generation = self.latest, self.generation
            try:
                jpeg, metadata = self.encoder.encode(frame)
                with self.condition:
                    self.latest_jpeg = (frame, jpeg, metadata)
                    self.jpeg_generation = generation
                    self.jpeg_encoded += 1
                    self.jpeg_error = None
                    self.condition.notifyAll()
            except Exception as exc:
                with self.condition:
                    self.jpeg_error = str(exc)
                    self.condition.notifyAll()
            consumed = generation

    def produce(self):
        while self.running:
            started = monotonic()
            if not self.paused:
                try:
                    frame = self.source.capture_pattern(timeout=2.0)
                    with self.condition:
                        self.latest = frame
                        self.latest_metadata = dict(getattr(self.source, 'last_metadata', {}))
                        self.generation += 1
                        self.captured += 1
                        self.error = None
                        self.condition.notifyAll()
                except Exception as exc:
                    with self.condition:
                        self.error = str(exc)
                        self.condition.notifyAll()
                    # Avoid hammering a failed MMIO device.
                    time.sleep(0.5)
            with self.condition:
                self.condition.wait(timeout=max(0.001, self.period - (monotonic() - started)))

    def metrics(self):
        with self.condition:
            frame = self.latest
            metrics = {
                "type": "status", "scene": getattr(self.source, 'scene', 'pattern'), "paused": self.paused,
                "source": frame.source if frame else "waiting",
                "error": self.error, "capture_fps": self.captured / max(0.001, monotonic() - self.started),
                "capture_fps_semantics": "session average including intentional capture pauses",
                "frames_captured": self.captured,
                "transport": "binary-websocket-rgb565", "encoding_ms": 0,
                "available_scenes": list(getattr(self.source, 'available_scenes', ['pattern'])),
                "note": getattr(self.source, 'note', "3D scenes are not integrated; pattern capture only"),
                "jpeg_enabled": self.encoder is not None,
                "jpeg_error": self.jpeg_error, "jpeg_frames_encoded": self.jpeg_encoded,
                "jpeg_last_client_ack_ms": self.jpeg_last_ack_ms,
            }
            if frame:
                metrics.update(sequence=frame.sequence, render_ms=(frame.render_seconds * 1000 if frame.clock_hz else None),
                               copy_ms=frame.copy_seconds * 1000,
                               capture_ms=frame.capture_seconds * 1000,
                               render_fps=(1.0 / frame.render_seconds if frame.render_seconds else None))
            if self.latest_jpeg:
                jpeg_frame, jpeg, details = self.latest_jpeg
                metrics.update(jpeg_sequence=jpeg_frame.sequence, jpeg_bytes=len(jpeg),
                               jpeg_encode_ms=details['mean_encode_ms'], jpeg_cpu_ms=details['cpu_ms'],
                               jpeg_conversion_ms=details['rgb_conversion_ms'],
                               jpeg_helper_wall_ms=details['helper_wall_ms'], jpeg_quality=details['quality'])
                metrics['jpeg_lib_version'] = details.get('jpeg_lib_version')
            metadata = self.latest_metadata
            now = monotonic()
            displays=[]
            for key, state in self.displays.items():
                times=[t for t in state['times'] if now-t<=5]
                fps=(len(times)-1)/(times[-1]-times[0]) if len(times)>1 and times[-1]>times[0] and now-times[-1]<1 else 0
                displays.append(dict(client=key,kind=state['kind'],acknowledged_fps=fps,frames=state['frames'],sequence=state.get('sequence'),send_ack_ms=state.get('send_ack_ms'),canvas_updated=state.get('canvas_updated',False),visible=state.get('visible',False)))
            metrics['display_clients']=displays
            if getattr(self.source, 'game_mode', False):
                metrics['simulation_paused'] = metadata.get('paused', True)
            if 'scene' in metadata:
                metrics['scene'] = metadata['scene']
            if hasattr(self.source, 'rotation_paused'):
                metrics['rotation_paused'] = self.source.rotation_paused
            for field in ('frame_timing', 'pipeline_busy_cycles', 'angle', 'depth_order', 'initialization_seconds', 'submission_mode', 'depth_test_enabled', 'tick', 'health', 'kills', 'distance', 'game_over', 'simulation_target_hz', 'triangles_submitted', 'gpu_sequence', 'sensor_fresh', 'sensor_ready', 'sensor_calibrating', 'sensor_samples', 'sensor_roll', 'sensor_pitch', 'geometry_ms', 'host_submit_ms', 'prepare_ms', 'readback_overlap', 'queued_syncs', 'command_submit_ms', 'drain_ms'):
                if field in metadata:
                    metrics[field] = metadata[field]
            if 'render_timing_semantics' in metadata:
                metrics['frame_timing'] = metadata['render_timing_semantics']
            for field in ('slot_wait_ms','owner_cpu_ms','previous_publish_ms','ready_wait_ms','scene_wait_ms','geometry_cpu_ms','prepare_cpu_ms','previous_submit_ms','readback_policy','readback_policy_error'):
                if field in metadata:metrics[field]=metadata[field]
            return metrics

    def control(self, message):
        if message.get('type') == 'game-input' and hasattr(self.source, 'control_input'):
            self.source.control_input(message)
            return
        if message.get('type') == 'pause' and isinstance(message.get('paused'), bool) and hasattr(self.source, 'set_game_pause'):
            self.source.set_game_pause(message['paused'])
            return
        if message.get('type') == 'pause' and isinstance(message.get('paused'), bool):
            with self.condition:
                self.paused = message['paused']
                self.condition.notifyAll()
            return
        if message.get('type') == 'scene':
            scene = message.get('scene')
            if scene not in getattr(self.source, 'available_scenes', ['pattern']):
                raise ValueError('Scene is not available from this FPGA producer')
            if hasattr(self.source, 'set_scene'):
                self.source.set_scene(scene)
            return
        if message.get('type') == 'rotation' and hasattr(self.source, 'set_rotation_paused') and isinstance(message.get('paused'), bool):
            self.source.set_rotation_paused(message['paused'])
            return
        raise ValueError('Unsupported diagnostic control')


class DisplayServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, hub):
        self.hub = hub
        self.client_slots = threading.BoundedSemaphore(4)
        self.input_slots = threading.BoundedSemaphore(4)
        # Bound ordinary HTTP threads too; a half-open HTTP request has a timeout.
        self.request_slots = threading.BoundedSemaphore(12)
        self.mjpeg_sessions = {}
        self.sessions_lock = threading.Lock()
        ThreadingHTTPServer.__init__(self, address, DisplayHandler)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.server_close()

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(False):
            request.close()
            return
        try:
            ThreadingHTTPServer.process_request(self, request, client_address)
        except BaseException:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            ThreadingHTTPServer.process_request_thread(self, request, client_address)
        finally:
            self.request_slots.release()


class DisplayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def address_string(self):
        # Python 2's default performs reverse DNS on every control heartbeat.
        return self.client_address[0]

    def log_request(self, code='-', size='-'):
        if self.path == '/control' and str(code) == '200':return
        BaseHTTPRequestHandler.log_request(self, code, size)

    def setup(self):
        BaseHTTPRequestHandler.setup(self)
        self.connection.settimeout(5.0)
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def response(self, payload, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if urlsplit(self.path).path == "/stream.mjpg":
            return self.mjpeg()
        if self.path == "/ws":
            return self.websocket()
        if self.path == "/input" and getattr(self.server.hub.source, 'game_mode', False):
            return self.websocket(input_only=True)
        if self.path == "/metrics":
            return self.response(json.dumps(self.server.hub.metrics()).encode(), "application/json")
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "application/javascript; charset=utf-8")}
        if self.path not in assets:
            return self.send_error(404)
        name, content_type = assets[self.path]
        if getattr(self.server.hub.source, 'game_mode', False):
            name = 'game.html' if name == 'index.html' else 'game.js'
        with open(os.path.join(WEB, name), "rb") as asset:
            self.response(asset.read(), content_type)

    def same_origin(self):
        origin = self.headers.get('Origin')
        return not origin or origin in ('http://' + self.headers.get('Host', ''),
                                        'https://' + self.headers.get('Host', ''))

    def do_POST(self):
        if not self.same_origin():
            return self.send_error(403, 'Cross-origin control rejected')
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if size < 0 or size > MAX_CONTROL:
                raise ValueError('Invalid control length')
            payload = json.loads(read_exact(self.rfile, size).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('Expected control object')
            if self.path == '/control':
                self.server.hub.control(payload)
                return self.response(b'{"ok":true}', 'application/json')
            if self.path == '/mjpeg-session':
                if self.server.hub.encoder is None:
                    return self.send_error(503, 'MJPEG encoder is not enabled')
                token = base64.urlsafe_b64encode(os.urandom(18)).decode('ascii')
                with self.server.sessions_lock:
                    # Abandoned session creation cannot consume slots indefinitely.
                    for old_token, state in list(self.server.mjpeg_sessions.items()):
                        if not state['active'] and monotonic() - state['created'] > 10:
                            del self.server.mjpeg_sessions[old_token]
                    if len(self.server.mjpeg_sessions) >= 16:
                        return self.send_error(503, 'Too many pending MJPEG sessions')
                    self.server.mjpeg_sessions[token] = dict(created=monotonic(), active=False,
                        condition=threading.Condition(), pending=None, acked=None)
                return self.response(json.dumps({'session': token, 'url': '/stream.mjpg?session=' + token}).encode(), 'application/json')
            if self.path == '/mjpeg-ack':
                with self.server.sessions_lock:
                    state = self.server.mjpeg_sessions.get(payload.get('session'))
                if state is None:
                    return self.send_error(404, 'MJPEG session expired')
                with state['condition']:
                    if payload.get('sequence') != state['pending'] or state['pending'] is None:
                        raise ValueError('Unexpected MJPEG acknowledgement')
                    state['acked'] = payload['sequence']
                    state['condition'].notifyAll()
                return self.response(b'{"ok":true}', 'application/json')
            return self.send_error(404)
        except (ValueError, TypeError, EOFError):
            self.close_connection = True
            return self.send_error(400, 'Invalid diagnostic control')

    def mjpeg(self):
        query = parse_qs(urlsplit(self.path).query)
        token = query.get('session', [''])[0]
        with self.server.sessions_lock:
            state = self.server.mjpeg_sessions.get(token)
            if state is None or state['active']:
                return self.send_error(404, 'Create an MJPEG session first')
            if not self.server.client_slots.acquire(False):
                return self.send_error(503, 'Four display clients already connected')
            state['active'] = True
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=gpu-frame')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.flush()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
            hub, generation = self.server.hub, -1
            while hub.running:
                with hub.condition:
                    while hub.running and (hub.latest_jpeg is None or hub.jpeg_generation == generation):
                        hub.condition.wait(timeout=0.25)
                    if not hub.running:
                        break
                    (frame, jpeg, details), generation = hub.latest_jpeg, hub.jpeg_generation
                with state['condition']:
                    state['pending'], state['acked'] = frame.sequence, None
                header = ('--gpu-frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n'
                          'X-Sequence: %d\r\nX-Source: %s\r\n\r\n') % (len(jpeg), frame.sequence, frame.source)
                started = monotonic()
                self.connection.sendall(header.encode('ascii') + jpeg + b'\r\n')
                deadline = monotonic() + 5
                with state['condition']:
                    while state['acked'] != frame.sequence and hub.running:
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            raise socket.timeout('MJPEG display acknowledgement deadline')
                        state['condition'].wait(timeout=min(.25, remaining))
                hub.jpeg_last_ack_ms = (monotonic() - started) * 1000
        except (OSError, IOError, EOFError, ValueError, socket.timeout):
            pass
        finally:
            with self.server.sessions_lock:
                self.server.mjpeg_sessions.pop(token, None)
            self.server.client_slots.release()

    def websocket(self, input_only=False):
        if self.headers.get("Upgrade", "").lower() != "websocket" or "upgrade" not in self.headers.get("Connection", "").lower():
            return self.send_error(400, "WebSocket upgrade required")
        if self.headers.get("Sec-WebSocket-Version") != "13":
            return self.send_error(400, "WebSocket version 13 required")
        # Browsers may control capture only from this server's own origin.
        origin = self.headers.get("Origin")
        if origin and origin not in ("http://" + self.headers.get("Host", ""), "https://" + self.headers.get("Host", "")):
            return self.send_error(403, "Cross-origin WebSocket rejected")
        key = self.headers.get("Sec-WebSocket-Key", "")
        try:
            decoded_key = base64.b64decode(key)
            if len(decoded_key) != 16 or base64.b64encode(decoded_key).decode("ascii") != key:
                raise ValueError("key")
        except (ValueError, binascii.Error):
            return self.send_error(400, "Invalid WebSocket key")
        slots = self.server.input_slots if input_only else self.server.client_slots
        if not slots.acquire(False):
            return self.send_error(503, "Four display clients already connected")
        self.close_connection = True
        display_id=None
        try:
            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            self.wfile.flush()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            generation = -1
            hub = self.server.hub
            if input_only:
                while hub.running:self.read_controls(None, input_only=True)
                return
            display_id=binascii.hexlify(os.urandom(6)).decode('ascii')
            with hub.condition:
                hub.displays[display_id]=dict(kind='browser' if self.headers.get('User-Agent','').startswith('Mozilla/') else 'protocol-probe',times=collections.deque(maxlen=300),frames=0)
            while hub.running:
                with hub.condition:
                    if hub.generation == generation or hub.latest is None:
                        hub.condition.wait(timeout=0.25)
                    frame, new_generation = hub.latest, hub.generation
                self.connection.sendall(websocket_packet(json.dumps(hub.metrics()).encode(), 1))
                if frame is None or new_generation == generation:
                    # Periodic ping also allows controls while capture is paused.
                    self.connection.sendall(websocket_packet(b"status", 9))
                    self.read_controls(None)
                    continue
                generation = new_generation
                started = monotonic()
                packet = websocket_packet(frame.to_wire())
                packed = monotonic()
                self.connection.sendall(packet)
                sent = monotonic()
                # Exactly one unacknowledged frame per client. Browser ACKs after
                # canvas update; producer can overwrite hub.latest while waiting.
                acknowledgement=self.read_controls(frame.sequence)
                hub.display_ack(display_id,acknowledgement,packed)
                self.connection.sendall(websocket_packet(json.dumps({"type": "delivery", "sequence": frame.sequence,
                    "send_ack_ms": (monotonic() - packed) * 1000,
                    "packet_prepare_ms": (packed - started) * 1000,
                    "socket_send_ms": (sent - packed) * 1000,
                    "wire_bytes": len(packet)}).encode(), 1))
        except (OSError, IOError, EOFError, ValueError, UnicodeError, socket.timeout):
            pass
        finally:
            if display_id is not None:
                with self.server.hub.condition:self.server.hub.displays.pop(display_id,None)
            slots.release()

    def read_controls(self, expected_sequence, input_only=False):
        deadline = monotonic() + 5.0
        while monotonic() < deadline:
            opcode, payload = receive_control(self.rfile)
            if opcode == 8:
                raise EOFError("close")
            if opcode == 9:
                self.connection.sendall(websocket_packet(payload, 10))
                continue
            if opcode == 10 and expected_sequence is None:
                return
            if opcode != 1:
                raise ValueError("unsupported message")
            message = json.loads(payload.decode("utf-8"))
            if not isinstance(message, dict):
                raise ValueError("expected object")
            if input_only and message.get('type') != 'game-input':
                raise ValueError('Control channel accepts only game input')
            if message.get("type") == "ack" and message.get("sequence") == expected_sequence:
                return message
            try:
                self.server.hub.control(message)
                if input_only:
                    ack={'type':'input-ack','sequence':message['input']['sequence']}
                    self.connection.sendall(websocket_packet(json.dumps(ack).encode('ascii'),1))
                    return
            except ValueError as exc:
                self.connection.sendall(websocket_packet(json.dumps({"type": "error", "error": str(exc)}).encode(), 1))
        raise socket.timeout("display acknowledgement deadline")


def main():
    def stop_service(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, stop_service)
    signal.signal(signal.SIGTERM, stop_service)
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", action="store_true", help="use real FPGA MMIO via /dev/mem")
    source.add_argument("--snapshot", help="replay raw RGB565 file (offline, no FPGA operation)")
    source.add_argument('--renderer-helper', help='explicit GPU2 native producer executable; requires verified 3D hardware image')
    source.add_argument('--game-frame', help='atomic frame exchange written by the on-board SpinalVoodoo game')
    parser.add_argument('--game-input-port', type=int, default=5522)
    parser.add_argument("--base", type=lambda value: int(value, 0), help="verified physical peripheral base (required for --device)")
    parser.add_argument("--span", type=lambda value: int(value, 0), default=0x27000)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--fps", type=float, default=15.0, help="capture rate cap, not promised throughput")
    parser.add_argument('--jpeg-helper', help='optional native jpeg_benchmark executable; enables shared MJPEG encoding')
    parser.add_argument('--jpeg-quality', type=int, default=75)
    parser.add_argument('--sidecar-base', type=lambda value: int(value, 0), help='explicit GPU2 sidecar physical base')
    parser.add_argument('--scene', choices=('pattern', 'triangle', 'depth', 'cube', 'textured-cube'))
    parser.add_argument('--angle', type=float, default=0)
    parser.add_argument('--angular-speed', type=float, default=30, help='native cube angle degrees per second; zero for deterministic diagnostics')
    parser.add_argument('--depth-order', choices=('far-first', 'near-first'), default='far-first')
    parser.add_argument('--renderer-process-timeout', type=float, default=15)
    args = parser.parse_args()
    if args.device and args.base is None:
        parser.error("--device requires --base from the generated hardware address map")
    if not 0 < args.fps <= 120:
        parser.error("--fps must be >0 and <=120")
    if args.game_frame:
        from game_source import GameFrameSource
        context = GameFrameSource(args.game_frame, args.game_input_port)
    elif args.renderer_helper:
        if args.base is None or args.sidecar_base is None:
            parser.error('--renderer-helper requires explicit --base and --sidecar-base from the generated map')
        if args.scene == 'pattern':
            parser.error('GPU2 native renderer does not implement the GPU1 pattern peripheral')
        from legacy_host import NativeRendererAdapter
        context = NativeRendererAdapter(args.base, args.sidecar_base, args.renderer_helper,
            scene=args.scene or 'triangle', angle=args.angle, angular_speed=args.angular_speed,
            depth_order=args.depth_order, process_timeout=args.renderer_process_timeout)
    else:
        if args.scene not in (None, 'pattern'):
            parser.error('3D scenes require an explicit native --renderer-helper')
        context = Device(args.base, span=args.span) if args.device else Snapshot(args.snapshot, width=args.width, height=args.height)
    with context as device:
        encoder = None
        if args.jpeg_helper:
            from jpeg_transport import NativeJPEGEncoder
            encoder = NativeJPEGEncoder(args.jpeg_helper, args.jpeg_quality)
        hub = FrameHub(device, args.fps, encoder=encoder)
        producer = threading.Thread(target=hub.produce, name="capture")
        producer.daemon = True
        producer.start()
        jpeg_thread = None
        if encoder:
            jpeg_thread = threading.Thread(target=hub.encode_latest, name='jpeg-encode')
            jpeg_thread.daemon = True
            jpeg_thread.start()
        with DisplayServer((args.bind, args.port), hub) as server:
            print("Display listening on http://%s:%s; source=%s" % (args.bind, args.port, "native GPU2 renderer" if args.renderer_helper else "hardware" if args.device else "OFFLINE SNAPSHOT"))
            sys.stdout.flush()
            try:
                server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:
                pass
            finally:
                with hub.condition:
                    hub.running = False
                    hub.condition.notifyAll()
                producer.join(timeout=3)
                if jpeg_thread:
                    jpeg_thread.join(timeout=3)


if __name__ == "__main__":
    main()
