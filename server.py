#!/usr/bin/env python3
"""Local, dependency-free Arduino serial → browser bridge (macOS / Linux)."""
import argparse
import collections
import glob
import json
import math
import os
from pathlib import Path
import select
import signal
import threading
import time
import termios
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent / "web"


def serial_ports():
    return sorted(set(p for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*",
                                        "/dev/ttyACM*", "/dev/ttyUSB*")
                      for p in glob.glob(pattern)))


class BoardBroker:
    def __init__(self, port=None, auto=True):
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.desired = auto
        self.port = port
        self.connected = False
        self.error = ""
        self.frame = None
        self.info = {}
        self.last_frame = 0
        self.times = collections.deque(maxlen=100)
        self.count = 0
        self.generation = 0
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def configure(self, enabled, port=None):
        with self.lock:
            self.desired = enabled
            if port is not None:
                self.port = port or None
            self.generation += 1
            self.frame = None
            self.info = {}
            self.last_frame = 0
            self.times.clear()
            self.count = 0
            self.connected = False
            self.error = ""

    def snapshot(self):
        with self.lock:
            age = time.monotonic() - self.last_frame if self.last_frame else None
            fresh = self.connected and age is not None and age < 2
            rate = ((len(self.times)-1)/(self.times[-1]-self.times[0])
                    if len(self.times)>1 and self.times[-1]>self.times[0] and fresh else 0)
            return dict(connected=self.connected, enabled=self.desired, fresh=fresh,
                        port=self.port, error=self.error, frame=self.frame,
                        info=self.info.copy(), age=age, rate=round(rate, 1), count=self.count,
                        generation=self.generation)

    def consume(self, line):
        try:
            obj = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(obj, dict):
            return
        with self.lock:
            if obj.get("t") == "i":
                self.info = obj
            elif obj.get("t") == "f" and all(
                isinstance(obj.get(k), (int, float)) and not isinstance(obj[k], bool)
                and math.isfinite(obj[k]) for k in ("ax", "ay", "az")
            ):
                self.frame = {k: obj[k] for k in ("ax", "ay", "az", "seq", "ms") if k in obj}
                self.last_frame = time.monotonic()
                self.times.append(self.last_frame)
                self.count += 1

    def run(self):
        while not self.stop.is_set():
            with self.lock:
                enabled, port, generation = self.desired, self.port, self.generation
            if not enabled:
                self.stop.wait(.1)
                continue
            if not port:
                ports = serial_ports()
                port = ports[0] if ports else None
            if not port:
                with self.lock:
                    self.error = "Chưa tìm thấy Arduino. Kiểm tra cáp USB."
                self.stop.wait(1)
                continue
            fd, original = None, None
            try:
                fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                # Cooperative lock: avoid two instances of this bridge sharing a port.
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                original = termios.tcgetattr(fd)
                attrs = termios.tcgetattr(fd)
                attrs[0] = attrs[1] = attrs[3] = 0
                attrs[2] = (attrs[2] & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB
                                        | getattr(termios, "CRTSCTS", 0))) | termios.CS8 | termios.CLOCAL | termios.CREAD
                attrs[4] = attrs[5] = termios.B115200
                attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
                with self.lock:
                    self.connected, self.error, self.port = True, "", port
                    self.frame, self.info, self.last_frame = None, {}, 0
                    self.times.clear()
                pending = b""
                while not self.stop.is_set():
                    with self.lock:
                        if self.generation != generation or not self.desired:
                            break
                    if not select.select([fd], [], [], .15)[0]:
                        continue
                    try:
                        data = os.read(fd, 8192)
                    except BlockingIOError:
                        continue
                    if not data:
                        raise OSError("Arduino đã ngắt kết nối.")
                    pending += data
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        self.consume(line)
                    if len(pending) > 65536:
                        pending = b""
            except (OSError, termios.error) as exc:
                with self.lock:
                    self.error = f"Không đọc được cổng USB: {exc}"
            finally:
                if fd is not None:
                    try:
                        if original is not None:
                            termios.tcsetattr(fd, termios.TCSANOW, original)
                    except (OSError, termios.error):
                        pass
                    os.close(fd)
                with self.lock:
                    self.connected = False
            self.stop.wait(.4)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith("POST"):
            super().log_message(fmt, *args)

    def reply(self, status, data, content_type="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/ports":
            return self.reply(200, serial_ports())
        if path == "/api/status":
            return self.reply(200, self.server.broker.snapshot())
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                while not self.server.broker.stop.is_set():
                    payload = json.dumps(self.server.broker.snapshot(), ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    self.server.broker.stop.wait(.05)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8"),
                 "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
                 "/control.mjs": ("control.mjs", "text/javascript; charset=utf-8"),
                 "/game.mjs": ("game.mjs", "text/javascript; charset=utf-8"),
                 "/game-view.mjs": ("game-view.mjs", "text/javascript; charset=utf-8")}
        if path not in files:
            return self.reply(404, {"error": "Not found"})
        filename, mime = files[path]
        self.reply(200, (ROOT / filename).read_bytes(), mime)

    def do_POST(self):
        # Only same-origin browser controls may operate the local USB bridge.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            return self.reply(403, {"error": "Origin không hợp lệ."})
        if urlparse(self.path).path != "/api/connection":
            return self.reply(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 2048:
                raise ValueError("Yêu cầu không hợp lệ.")
            obj = json.loads(self.rfile.read(length))
            if not isinstance(obj, dict) or not isinstance(obj.get("enabled"), bool):
                raise ValueError("Thiếu trạng thái kết nối.")
            port = obj.get("port")
            if port is not None and (not isinstance(port, str) or (port and port not in serial_ports())):
                raise ValueError("Hãy chọn một cổng USB trong danh sách.")
            self.server.broker.configure(obj["enabled"], port)
            self.reply(200, self.server.broker.snapshot())
        except (ValueError, TypeError):
            self.reply(400, {"error": "Yêu cầu không hợp lệ. Làm mới danh sách cổng USB."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Local HTTP port")
    parser.add_argument("--serial", help="USB serial device; otherwise auto-detect")
    parser.add_argument("--no-auto", action="store_true", help="Start with USB disconnected")
    args = parser.parse_args()
    broker = BoardBroker(args.serial, not args.no_auto)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        broker.close()
        raise
    server.broker = broker
    server.daemon_threads = True
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    print(f"AERO Escape Run → http://127.0.0.1:{server.server_port}", flush=True)
    print("USB 115200 baud · Ctrl+C để dừng", flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        broker.close()
        server.server_close()


if __name__ == "__main__":
    main()
