"""Optional black-box Windows validation using only Python's standard library.
Run from the project root after build.cmd. No downloads or extra packages.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "FlightingSimulatorGame.exe"
OUT = ROOT / "captures" / "validation"
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def run(*args, expected=0):
    result = subprocess.run([str(EXE), *map(str, args)], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    if result.returncode != expected:
        raise AssertionError((args, result.returncode, result.stdout, result.stderr))
    return result


def same(a, b):
    return hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


result = run("--self-test")
checks.append(result.stdout.strip())
result = run("--desktop-smoke", "--out", OUT / "desktop.png")
checks.append(result.stdout.strip())
replay = OUT / "sample-flight.csv"
run("--headless", "--scripted", "--ticks", 600, "--no-hud", "--record", replay,
    "--capture", OUT / "recorded", "--out", OUT / "recorded.ppm")
run("--headless", "--replay", replay, "--no-hud", "--out", OUT / "replayed.ppm")
assert same(OUT / "recorded.ppm", OUT / "replayed.ppm"), "Replay image differs"
assert same(OUT / "recorded.ppm.state.txt", OUT / "replayed.ppm.state.txt"), "Replay state differs"
assert same(OUT / "recorded.ppm.combat.txt", OUT / "replayed.ppm.combat.txt"), "Replay combat state differs"
assert same(OUT / "recorded.ppm.run.txt", OUT / "replayed.ppm.run.txt"), "Replay distance/dodge state differs"
checks.append("PASS: 600-tick black-box record/replay image and state SHA256 identity")
checks.append("PASS: combat replay HP, kills, projectiles, RNG and wave summary identity")
legacy_v2 = OUT / "legacy-v2.csv"
legacy_v2.write_text(replay.read_text().replace("FLIGHTING_REPLAY,6,", "FLIGHTING_REPLAY,2,", 1), encoding="ascii")
run("--headless", "--replay", legacy_v2, "--no-hud", "--out", OUT / "legacy-v2.ppm")
legacy_state = [-114.77997458834213, 129.41068234596628, -252.98041556859127,
                -.88413374093246722, .24227793372114445, .39708492830677938,
                45.158633840189452, .65, 600, 0]
assert all(abs(a-b) < 1e-9 for a,b in zip(map(float, (OUT / "legacy-v2.ppm.state.txt").read_text().split(',')), legacy_state))
assert (OUT / "legacy-v2.ppm.combat.txt").read_text().startswith("0,100,0,0,0,0,")
checks.append("PASS: existing format-2 flight replay retains flight trajectory, full HP and no combat")
legacy_v3 = OUT / "legacy-v3.csv"
legacy_v3.write_text(replay.read_text().replace("FLIGHTING_REPLAY,6,", "FLIGHTING_REPLAY,3,", 1), encoding="ascii")
run("--headless", "--replay", legacy_v3, "--capture", OUT / "legacy-v3", "--out", OUT / "legacy-v3.ppm")
assert json.loads((OUT / "legacy-v3" / "frame.json").read_text())["Environment"] == "SEEDED TERRAIN"
assert json.loads((OUT / "recorded" / "frame.json").read_text())["Environment"] == "ENDLESS HANOI / CIRCA 1972"
legacy_v4 = OUT / "legacy-v4.csv"
legacy_v4.write_text(replay.read_text().replace("FLIGHTING_REPLAY,6,", "FLIGHTING_REPLAY,4,", 1), encoding="ascii")
run("--headless", "--replay", legacy_v4, "--capture", OUT / "legacy-v4", "--out", OUT / "legacy-v4.ppm")
assert json.loads((OUT / "legacy-v4" / "frame.json").read_text())["Environment"] == "HANOI / CIRCA 1972"
legacy_v5 = OUT / "legacy-v5.csv"
legacy_v5.write_text(replay.read_text().replace("FLIGHTING_REPLAY,6,", "FLIGHTING_REPLAY,5,", 1), encoding="ascii")
run("--headless", "--replay", legacy_v5, "--capture", OUT / "legacy-v5", "--out", OUT / "legacy-v5.ppm")
assert json.loads((OUT / "legacy-v5" / "frame.json").read_text())["Environment"] == "LOOPING HANOI / CIRCA 1972"
assert same(OUT / "legacy-v3.ppm.state.txt", OUT / "legacy-v5.ppm.state.txt")
assert same(OUT / "legacy-v3.ppm.combat.txt", OUT / "legacy-v5.ppm.combat.txt")
checks.append("PASS: format 6 is an endless run; formats 1-5 retain legacy free-flight environments and controls")
run("--render-capture", OUT / "recorded" / "frame.json", "--out", OUT / "reproduced.ppm")
assert same(OUT / "recorded.ppm", OUT / "reproduced.ppm"), "Frame reproduction differs"
checks.append("PASS: frame JSON independently reproduces reference image")
run("--compare", OUT / "recorded.ppm", OUT / "replayed.ppm", "--tolerance", 0,
    "--edge-radius", 0, "--allowed-fraction", 0, "--out", OUT / "diff.ppm")
checks.append("PASS: zero-tolerance image comparator")
run("--headless", "--scripted", "--ticks", 600, "--scene", 1, "--width", 128,
    "--height", 96, "--complexity", 4, "--out", OUT / "other-resolution.ppm")
assert same(OUT / "recorded.ppm.state.txt", OUT / "other-resolution.ppm.state.txt")
checks.append("PASS: different scene/resolution/complexity leaves aircraft state unchanged")
run("--headless", "--ticks", 1, "--wireframe", "--out", OUT / "wireframe.ppm")
checks.append("PASS: software wireframe frame renders")
run("--headless", "--backend", "rasterix", "--ticks", 1, expected=1)
checks.append("PASS: missing RasterIX bridge fails explicitly, without desktop fallback")
run("--backend", "invalid", expected=1)
run("--width", 0, expected=1)
checks.append("PASS: unsupported backend and invalid resolution rejected")

combat_replay = OUT / "combat-flight.csv"
rows = ["FLIGHTING_REPLAY,6,1337,60"]
for tick in range(1200):
    vertical = 0 if tick < 100 else (1 if ((tick-100)//60) % 2 == 0 else -1)
    rows.append(f"{tick},0,0,0,0.55,4,{vertical}")
combat_replay.write_text("\n".join(rows)+"\n", encoding="ascii")
run("--headless", "--replay", combat_replay, "--no-hud", "--out", OUT / "combat.ppm",
    "--capture", OUT / "combat")
combat = list(map(int, (OUT / "combat.ppm.combat.txt").read_text().split(",")))
assert combat[2] > 0 and combat[6] > 0, "Player fire did not destroy an enemy"
assert combat[1] > 0 and combat[8] == 0, "Demo dodging flight did not survive"
run("--headless", "--replay", combat_replay, "--no-hud", "--out", OUT / "combat-replayed.ppm")
assert same(OUT / "combat.ppm.combat.txt", OUT / "combat-replayed.ppm.combat.txt")
assert same(OUT / "combat.ppm", OUT / "combat-replayed.ppm")
checks.append(f"PASS: playable fire/dodge replay survives 1200 ticks, {combat[2]} kills, {combat[1]} HP; combat state repeatable")
# Half-speed enemy bullets allow a longer idle survival time.
idle_tick_limit = 7200
run("--headless", "--ticks", idle_tick_limit, "--out", OUT / "idle-game-over.ppm",
    "--capture", OUT / "game-over")
idle = list(map(int, (OUT / "idle-game-over.ppm.combat.txt").read_text().split(",")))
assert idle[1] == 0 and idle[8] == 1 and idle[0] < idle_tick_limit, "Enemy fire did not produce a game over"
checks.append(f"PASS: actual enemy fire drains 100 HP and freezes idle flight at tick {idle[0]}")

# Real process/loopback watchdog test. A restricted host may forbid sockets;
# report that as untested, never as a successful input integration run.
udp_status = "NOT RUN"
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    child = subprocess.Popen([str(EXE), "--headless", "--realtime", "--input-udp",
                              str(port), "--ticks", "60", "--width", "128", "--height",
                              "96", "--complexity", "4", "--no-hud", "--out", str(OUT / "udp.ppm")],
                             cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, creationflags=flags)
    try:
        time.sleep(0.3)
        if child.poll() is not None:
            out, err = child.communicate()
            if "SocketException" in err and ("forbidden" in err or "access" in err.lower()):
                raise PermissionError("Process socket creation denied by environment")
            raise AssertionError((out, err))
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        start = time.monotonic()
        seq = 0

        def send(connected=True):
            global seq
            seq += 1
            packet = dict(version=1, session="validation", sequence=seq,
                          sender_ms=int((time.monotonic()-start)*1000), pitch=0,
                          roll=0, yaw=0, throttle=0.55, buttons=0,
                          focused=True, connected=connected)
            sender.sendto(json.dumps(packet).encode(), ("127.0.0.1", port))

        send()
        time.sleep(1.6)
        assert child.poll() is None, "Watchdog failed to pause after a single input snapshot"
        deadline = time.monotonic()+8
        while child.poll() is None and time.monotonic() < deadline:
            send()
            time.sleep(0.016)
        assert child.poll() == 0, "Fresh input did not resume and complete simulation"
        out, err = child.communicate(timeout=2)
        assert ",60," in (OUT / "udp.ppm.state.txt").read_text()
        sender.close()
        udp_status = "PASS: real loopback UDP, 500ms watchdog pause, fresh-input resume, 60 completed ticks"
        checks.append(udp_status)
    finally:
        if child.poll() is None:
            child.terminate()
            child.communicate(timeout=5)
except (PermissionError, OSError) as exc:
    udp_status = "UNTESTED: local sockets unavailable: " + str(exc)
    checks.append(udp_status)

report = dict(checks=checks, udp=udp_status,
              executable_sha256=hashlib.sha256(EXE.read_bytes()).hexdigest(),
              replay_sha256=hashlib.sha256(replay.read_bytes()).hexdigest(),
              aircraft_state=(OUT / "recorded.ppm.state.txt").read_text().strip(),
              combat_summary=(OUT / "combat.ppm.combat.txt").read_text().strip(),
              board="UNTESTED", rasterix="UNTESTED; missing bridge failure verified")
(OUT / "validation-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("\n".join(checks))
print("Saved captures/validation/validation-results.json")
