# Game / USB integration handoff — 2026-11-07

> Historical handoff. Current software, fidelity gates and measured limits are
> documented in [the 2026-11-08 software audit](SOFTWARE_PROFILE.md). The reduced
> scenery and serialized-default descriptions below describe the earlier build.

Repository: `D:\GPU_proj\hackRPI`, cloned from kaitophuc/hackRPI at
`6b55fee2fd837894c211b46652201583ec096488`.

The 3D combat game runs on the DE10 ARM HPS, renders through the actual
SpinalVoodoo FPGA GPU2, and serves its pixels at
**http://169.254.170.29:8081/**. Arduino UNO R4 WiFi + MMA7660 is detected,
streaming, and integrated into the existing tilt controller. Keyboard/touch
play remains available. Calibration and input-loss pausing pass live tests.
The game is left running and paused after testing. Refresh the web page,
hold your grip steady, and use CALIBRATE & PLAY to set your own center.

**Performance remains incomplete.** The user correctly reported lag. Recent
captures deliver roughly 2–4 FPS under these test conditions, not 30 FPS.
A six-sample paused measurement gave 4.019 captured FPS, with median geometry
15.416 ms, host submission 164.989 ms, native render/submission 104.448 ms,
and readback 45.693 ms. Individual frames vary substantially. Native
`render_fps` is not end-to-end or displayed FPS.

Changes already applied: bounded native diagnostics with idle spam suppressed;
lower neighbourhood detail/range; FPGA font-atlas HUD; exact pixel comparison
instead of per-frame texture hashing; fixed-step input polling at 125 Hz;
binary private loopback controls; dedicated browser input WebSocket independent
of display acknowledgements; reverse-DNS logging removed from control requests.
These improve overhead but do not resolve the remaining frame-rate limitation.

Validated:

- 425 portable C# checks and 426 Windows desktop checks pass on the computer.
- Five sensor framing/freshness/control validation tests pass.
- Actual board smoke: live sensor -> calibration -> game ticks/firing -> GPU2
  frames -> focus loss pauses. Latest run advanced 159 simulation ticks;
  another run recorded a kill. Hand-motion direction still merits user testing
  with their normal grip and reversal preferences.
- Actual board sensor-only managed probe passed with 13 unique live samples.
- Seven of eight identical hardware captures matched between serialized and
  queued submission; terrain scene 6 differed. Queued mode remains disabled.
- Prior W16 combat comparison missed the proposed reference threshold:
  826/76800 mismatched pixels (1.076%, threshold 1%). No full graphics-contract
  conformance claim is made.

The earlier baseline portable suite passed 420 checks on ARM before these
latest changes. A subsequent broad ARM test was stopped because it competed
with live gameplay; do not describe the latest 425-check suite as ARM-tested.
Current live integration tests run on the actual board.

GPU/platform sources are copied into `fpga/`, including the accepted GPU2
Standard RTL, project, generated ROMs and local SOF. Prepared Glide source is
copied into `fpga/build/spinal-native-src` on both the computer and board;
the board's existing tested static library was copied and compared exactly.
The game build now uses this repository's source path. The accepted FPGA image
is unchanged. The old `/root/de10_gpu_platform` project remains a rollback.

Runtime/services, deployment and known limitations are documented in
[DE10_GAME.md](../docs/DE10_GAME.md). Raw evidence:
[sensor/game smoke](de10-sensor-smoke.json),
[timing samples](de10-performance.json),
[queued comparison](de10-batch-comparison.json), and
[FPGA pixel capture](de10-game.png).

Next performance work: profile ARM preparation/submission and readback under
active control, then address the GPU command-queue correctness problem before
enabling queued terrain rendering. Do not replace FPGA rasterization with a
software/browser renderer to claim a frame-rate result.
