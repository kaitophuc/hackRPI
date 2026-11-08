# DE10-Standard LAN graphics platform

The DE10-Standard runs the AERO game with ARM HPS simulation, SpinalVoodoo FPGA
rasterization and Arduino tilt controls. The browser at
<http://169.254.170.29:8081/> displays exact captured 320x240 RGB565 pixels.
The latest continuous visible-play test measured **16.27 displayed FPS**;
the 27 FPS minimum remains unmet. The selected queued renderer passed 360
frame comparisons against 28 pre-change FPGA references with zero additional
pixel differences. The existing CPU-vs-FPGA reference mismatch is documented.

See the [game/board guide](../combat/docs/DE10_GAME.md),
[requirements audit](../combat/reports/SOFTWARE_COMPLETION_AUDIT.md) and
[checkpoint evidence](../combat/reports/evidence/2026-11-08/README.md).
The standalone cube and pattern paths remain available as diagnostic tools.

The [recovery backup](../recovery/README.md) includes the accepted FPGA SOF,
matching game/native/Mono runtimes and pinned upstream source directly in Git.

The selected renderer is **SpinalVoodoo**, pinned in
[dependencies.lock.json](dependencies.lock.json). Its native ARM Glide stack,
framebuffer readback and Avalon interfaces offer the shortest credible 3D port.
Its original board flow targets the Nano; this workspace adds a separate
Standard GPU2 project and explicit publication/readback fence. The original
GPU1 test-pattern project remains available as a fallback.
[The candidate comparison](docs/core-selection.md) explains the choice,
dependencies, licenses and remaining port work.

```text
ARM-native Glide commands → FPGA raster/depth/texture pipeline → DDR
                                                               ↓
                                               fenced native LFB readback
                                                               ↓
                                                HPS private RGB565 copy
                                                               ↓
                                             latest-only binary WebSocket
                                                               ↓
                                                 laptop canvas display
```

The target is 320×240 RGB565. Completed frames stay locked until the HPS copies
and releases them. Network clients receive the private HPS copy and never hold
FPGA memory ownership. The diagnostic producer serializes rendering and copy.
No VGA monitor or video encoder is required. The browser performs pixel
conversion/display only. GPU2 build, native diagnostics and boot-specific DDR
guards are documented in [software/spinal/README.md](software/spinal/README.md).

| Component | Source / instructions |
|---|---|
| Exact Standard device, pins, HPS, build/program | [Hardware guide](docs/hardware.md), [build script](hardware/build.ps1) |
| GPU2 renderer build, warm boot, DDR audit and live service | [Standard GPU2 runbook](docs/spinal-standard-bringup.md) |
| Byte address map, pixel and wire format, ownership | [Interface contract](docs/interface.md) |
| Memory architecture and planned renderer integration | [Architecture](docs/architecture.md) |
| Native MMIO helper, capture API, Linux checks | [HPS guide](docs/hps.md), [host.py](software/host.py) |
| HTTP page, WebSocket, controls and metrics | [Streaming guide](docs/streaming.md), [server.py](software/server.py) |
| Tests, evidence definitions and all milestone gates | [Verification guide](docs/verification.md) |

Reproduce the Windows tests (Python 3.7+ and Icarus required):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-deps.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tests.ps1 -Python C:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe
powershell -NoProfile -ExecutionPolicy Bypass -File hardware/build.ps1 -QuartusRoot D:/Quartus/quartus
```

For the separate GPU1 pattern fallback, after a successful build/program and confirmation that Linux has the
matching HPS handoff and enabled LW bridge, copy `software/` to the board. Check
the generated address map before using this project's intended base:

```sh
cd software
sh build_mmio.sh
sudo python3 host.py --base 0xff240000 --check-pattern --output frame.rgb565
sudo python3 server.py --device --base 0xff240000 --port 8080 --fps 15
```

Open `http://BOARD_LAN_IP:8080/` on the laptop. Expected capture: 153600 bytes,
`pattern_checked: true`, `source: hardware`. Preserve the capture JSON and boot
logs. The source banner distinguishes hardware from offline replay.

For a software-only protocol demonstration using the RTL simulation dump:

```powershell
C:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe software/server.py --snapshot reports/simulated-frame.rgb565 --bind 127.0.0.1 --port 8080
```

This replays a simulated framebuffer and cannot count as board bring-up.
Rendering and capture throughput, browser FPS, copy cost and transfer/ACK cost
are recorded separately. The 15 FPS option is a cap, not a performance claim.
Raw WebSocket is provisional; [the measurement procedure](docs/streaming.md)
defines when to compare MJPEG on the HPS.

The supported diagnostic milestones now include triangles, depth, solid and
textured cubes, and continuous LAN display. Queued submission and 30 FPS
capture remain future engineering work; see the verified result's limits. DDR use
depends on the documented audit of the current boot; there is no persistent
device-tree carveout yet. [Attribution](THIRD_PARTY.md) covers reused sources.
