"""Verify real RGB565 frames over WebSocket and record delivered-rate evidence."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import statistics
import struct
import time
import urllib.request


def exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise EOFError('display disconnected')
    return data


def masked(sock, payload, opcode=1):
    if len(payload) >= 126:
        raise ValueError('probe controls must be short')
    mask = os.urandom(4)
    body = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
    sock.sendall(bytes((0x80 | opcode, 0x80 | len(payload))) + mask + body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--ack-delay', type=float, default=0, help='simulate a slow consumer')
    parser.add_argument('--reference', type=Path, default=Path('reports/simulated-frame.rgb565'))
    parser.add_argument('--rotating-cube', action='store_true', help='validate changing opaque cube frames instead of a fixed reference')
    parser.add_argument('--sequence-step', type=int, default=1, help='expected publication sequence increment per captured frame (GPU2 uses 2)')
    parser.add_argument('--link-speed-mbps', type=int, help='operator-observed link speed for this run; not inferred from throughput')
    parser.add_argument('--output', type=Path, default=Path('reports/lan-measurement.json'))
    parser.add_argument('--frame', type=Path, default=Path('reports/hardware-frame.rgb565'))
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error('seconds must be 1..120')
    if not 0 <= args.ack_delay <= 3:
        parser.error('ack delay must be 0..3 seconds')
    if args.sequence_step < 1:
        parser.error('sequence step must be positive')
    expected = None if args.rotating_cube else args.reference.read_bytes()
    expected_size = 153600 if expected is None else len(expected)
    frames, deliveries, times = [], [], []
    frame_hashes, angles = set(), set()
    status = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def producer_metrics():
        with opener.open('http://%s:%d/metrics' % (args.host, args.port), timeout=5) as response:
            return json.load(response)
    producer_started = time.monotonic()
    producer_before = producer_metrics()
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.settimeout(5)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(('GET /ws HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n'
                      'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                      'Sec-WebSocket-Key: %s\r\n\r\n' % (args.host, args.port, key)).encode())
        with sock.makefile('rb') as stream:
            if b' 101 ' not in stream.readline():
                raise RuntimeError('WebSocket handshake rejected')
            headers = {}
            while True:
                line = stream.readline()
                if line == b'\r\n':
                    break
                if not line:
                    raise EOFError('incomplete handshake')
                name, value = line.decode().split(':', 1)
                headers[name.lower()] = value.strip()
            accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if headers.get('sec-websocket-accept') != accept:
                raise RuntimeError('invalid WebSocket accept')
            started = time.monotonic()
            while time.monotonic() - started < args.seconds:
                first, second = exact(stream, 2)
                if not first & 0x80 or second & 0x80:
                    raise RuntimeError('unsupported server frame')
                opcode, length = first & 15, second & 127
                if length == 126:
                    length = struct.unpack('!H', exact(stream, 2))[0]
                elif length == 127:
                    length = struct.unpack('!Q', exact(stream, 8))[0]
                if length > 1024 * 1024:
                    raise RuntimeError('server payload exceeds probe bound')
                payload = exact(stream, length)
                if opcode == 9:
                    masked(sock, payload, 10)
                elif opcode == 1:
                    message = json.loads(payload)
                    if message.get('type') == 'status':
                        status = message
                    elif message.get('type') == 'delivery':
                        deliveries.append(message)
                elif opcode == 2:
                    magic, sequence, width, height, fmt, size = struct.unpack('<4sIIIII', payload[:24])
                    if (magic, width, height, fmt, size) != (b'GPU1', 320, 240, 1, expected_size) or len(payload) != 24 + size:
                        raise RuntimeError('hardware frame geometry/format mismatch')
                    pixels = payload[24:]
                    if expected is not None and pixels != expected:
                        raise RuntimeError('hardware pixels differ from verified reference')
                    if not status or status.get('source') != 'hardware':
                        raise RuntimeError('stream is not marked hardware')
                    if args.rotating_cube:
                        colors = struct.unpack('<76800H', pixels)
                        if status.get('scene') != 'cube' or status.get('rotation_paused') or status.get('paused'):
                            raise RuntimeError('expected an actively rotating cube producer')
                        if not set(colors).issubset({0, 0xf800, 0x07e0, 0x001f, 0xffe0, 0x07ff, 0xf81f}):
                            raise RuntimeError('solid cube contains unexpected colors')
                        if not 1000 < sum(value != 0 for value in colors) < 40000 or colors[120 * 320 + 160] == 0:
                            raise RuntimeError('cube unexpectedly empty, oversized or missing its center')
                        if any(colors[y * 320 + x] for x, y in ((10,10),(310,10),(10,230),(310,230))):
                            raise RuntimeError('cube corrupts clear exterior')
                        frame_hashes.add(hashlib.sha256(pixels).hexdigest())
                        if status.get('sequence') == sequence:
                            angles.add(status.get('angle'))
                    if frames and sequence == frames[-1]:
                        raise RuntimeError('sequence did not advance')
                    if not frames:
                        args.frame.write_bytes(payload[24:])
                    frames.append(sequence)
                    times.append(time.monotonic())
                    if args.ack_delay:
                        time.sleep(args.ack_delay)
                    masked(sock, json.dumps({'type': 'ack', 'sequence': sequence}).encode())
                elif opcode == 8:
                    raise EOFError('server closed display')
            masked(sock, struct.pack('!H', 1000), 8)
    elapsed = time.monotonic() - started
    if len(frames) < 2:
        raise RuntimeError('fewer than two hardware frames delivered')
    deltas = [(right - left) & 0xffffffff for left, right in zip(frames, frames[1:])]
    if any(delta < args.sequence_step or delta % args.sequence_step for delta in deltas):
        raise RuntimeError('unexpected publication sequence cadence')
    if args.rotating_cube and min(len(frame_hashes), len(angles)) < 2:
        raise RuntimeError('cube frames or producer angles did not change')
    producer_after = producer_metrics()
    producer_elapsed = time.monotonic() - producer_started
    producer_count = producer_after['frames_captured'] - producer_before['frames_captured']
    result = dict(source='hardware', host=args.host, port=args.port,
                  observed_link_speed_mbps=args.link_speed_mbps,
                  duration_seconds=elapsed, frames_received=len(frames),
                  consumer_ack_delay_seconds=args.ack_delay,
                  delivered_fps=(len(frames) - 1) / (times[-1] - times[0]),
                  raw_payload_mbps=len(frames) * expected_size * 8 / elapsed / 1e6,
                  first_sequence=frames[0], last_sequence=frames[-1],
                  sequence_step=args.sequence_step,
                  raw_sequence_gaps=sum(delta - 1 for delta in deltas),
                  skipped_sequences=sum(delta // args.sequence_step - 1 for delta in deltas),
                  every_pixel_matches_reference=expected is not None,
                  sha256=hashlib.sha256(expected).hexdigest() if expected is not None else None,
                  rotating_cube=args.rotating_cube, unique_frame_hashes=len(frame_hashes), unique_angles=len(angles),
                  observed_producer_frames=producer_count, observed_producer_fps=producer_count/producer_elapsed,
                  last_status=status,
                  mean_send_ack_ms=statistics.mean(d['send_ack_ms'] for d in deliveries) if deliveries else None,
                  mean_packet_prepare_ms=statistics.mean(d['packet_prepare_ms'] for d in deliveries) if deliveries else None,
                  mean_socket_send_ms=statistics.mean(d['socket_send_ms'] for d in deliveries) if deliveries else None,
                  note=('LAN socket consumer ACKs after cube scene checks; fixed-scene exact pixel and browser tests are separate'
                        if args.rotating_cube else 'LAN socket consumer ACKs after exact pixel comparison; browser FPS is measured separately'))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
