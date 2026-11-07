#!/usr/bin/env python3
"""Build and play the desktop dogfight with this repo's Arduino sensor bridge."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.error import URLError
from urllib.request import Request, urlopen

from server import BoardBroker, Handler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
GAME = ROOT / "combat"
EXE = GAME / "dist" / "FlightingSimulatorGame.exe"


def build_game(force=False):
    sources = [GAME / "build.ps1", *sorted((GAME / "src").glob("*.cs"))]
    if force or not EXE.exists() or any(path.stat().st_mtime > EXE.stat().st_mtime for path in sources):
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(GAME / "build.ps1")], cwd=GAME, check=True)
    return EXE


def ensure_bridge(port, serial_port=None):
    """Reuse a compatible running bridge, or start one owned by this launcher."""
    base = f"http://127.0.0.1:{port}"
    try:
        with urlopen(base + "/api/status", timeout=1) as response:
            status = json.load(response)
    except URLError:
        # Binding still rejects an occupied port; never terminate another server.
        http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        http.daemon_threads = True
        try:
            http.broker = BoardBroker(serial_port)
        except Exception:
            http.server_close()
            raise
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        return base, (http, worker)
    if not isinstance(status, dict) or not {"enabled", "generation", "frame", "fresh"}.issubset(status):
        raise RuntimeError(f"Another application is using port {port}; choose --port 8766.")
    if not status["enabled"] or (serial_port and serial_port != status.get("port")):
        payload = {"enabled": True}
        if serial_port:
            payload["port"] = serial_port
        request = Request(base + "/api/connection", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=2) as response:
            response.read()
    return base, None


def close_bridge(owned):
    if owned:
        http, worker = owned
        http.broker.close()
        http.shutdown()
        http.server_close()
        worker.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Arduino COM port; default auto-detect")
    parser.add_argument("--port", type=int, default=8765, help="Local sensor server port")
    parser.add_argument("--build", action="store_true", help="Force rebuilding the desktop game")
    parser.add_argument("--build-only", action="store_true", help="Build without opening the game")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("The combat desktop game requires Windows and .NET Framework 4.x.")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    owned, game = None, None
    try:
        executable = build_game(args.build)
        if args.build_only:
            return 0
        base, owned = ensure_bridge(args.port, args.serial)
        print("Hold the sensor in your normal grip, then click CALIBRATE & PLAY at the top of the game.", flush=True)
        print("Auto-forward endless flight: tilt to dodge sideways/up/down. Hold F or left mouse to fire.", flush=True)
        game = subprocess.Popen([str(executable), "--accelerometer", base + "/"], cwd=GAME)
        return game.wait()
    except KeyboardInterrupt:
        if game and game.poll() is None:
            game.terminate()
            game.wait(timeout=5)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Unable to start combat game: {exc}", file=sys.stderr)
        return 1
    finally:
        close_bridge(owned)


if __name__ == "__main__":
    raise SystemExit(main())
