# DE10-Standard game and Arduino controls

The `combat/` 3D game now has a dedicated SpinalVoodoo backend. The ARM HPS
runs the C# simulation, builds and clips geometry, reads the USB Arduino, and
submits triangles. The FPGA rasterizes triangles, textures, depth and HUD to
320x240 RGB565. The browser displays captured FPGA pixels and sends controls.
There is no software-rendering fallback in the `spinal` backend.

## Play on the current board

Open **http://169.254.170.29:8081/** from the directly connected computer or
iPad. The peer needs a compatible 169.254.x.x/16 Ethernet address. Refresh
after a software update. The computer is not needed as a rendering server.

For the Arduino MMA7660, hold your normal grip, press **CALIBRATE & PLAY**,
and keep steady for 1.8 seconds. The page reports calibration and live tilt.
Use the reversal checkboxes if needed. **F** or the touch **FIRE** button shoots.
Uncheck **Use Arduino tilt** to use WASD/arrows and **Play / Resume** instead.
Switching away, losing control heartbeats, or stale tilt input pauses play.
A disconnected or restarted Arduino requires calibration again.

The USB host detects Arduino UNO R4 WiFi VID:PID `2341:1002`. The existing
firmware reports MMA7660 / `wifi-diag-3`. The board's Linux 4.5 kernel has
`CONFIG_USB_ACM` disabled, so `arduino_usb.py` uses the installed libusb to
claim only CDC interfaces 1/2 and receive endpoint 0x84. It leaves the HID
debugger alone. It sets 115200 8N1 and DTR/RTS; it never flashes the
Arduino or sends application commands. Interface numbers/endpoints are
discovered rather than assumed when opening the device.

Browser input uses a dedicated control WebSocket, separate from frame ACKs.
The server validates JSON and forwards a fixed 102-byte private loopback
packet (`<4s32sqq5dI6B`, magic `SFI1`) to the managed input gate. Legacy JSON
UDP input remains supported. Both paths retain sequence/session validation
and the 500 ms control watchdog.

The broker publishes bounded, atomic snapshots in
`/dev/shm/hackrpi-game/sensor.json`. The game reuses the desktop's tested
TiltController. The optional loopback HTTP status endpoint remains
`http://127.0.0.1:8765/api/status`; the board game uses the file because Mono's
HTTP client timed out on this Linux image. Duplicate sample sequence numbers
cannot keep the sensor fresh. Freshness expires after 750 ms.

## Start, stop and deploy

On the board:

```sh
cd /root/hackrpi
sh combat/board/start_service.sh
python combat/board/stop_service.py
```

Start stops the previous owned services, audits the current DDR configuration,
then starts the sensor, game and web services. Stop requests a graceful game
exit so GPU fences/readback can finish. Do not run two GPU producers together.
The FPGA image and DDR configuration are not programmed by these scripts.

On Windows, from this repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File combat/board/build.ps1 -Test
python combat/tests/board_sensor_test.py
python combat/board/deploy.py --start
```

Deployment uses SSH/SCP to the current board and builds the native C bridge
with its ARM compiler. It verifies the uploaded bundle checksum before
extracting. The tested Glide source/static library is copied inside
`/root/hackrpi/fpga/build/spinal-native-src/emu/glide`; runtime/build no longer
requires the old project path. The matching prepared source is also copied
under the computer's `fpga/build/spinal-native-src`. Generated sources and
accepted build outputs remain ignored in their working directories. A complete
accepted SOF/runtime/source copy is tracked separately under `recovery/`; follow
the [fresh-clone recovery guide](../../recovery/README.md) to restore it without
the old computer workspace or external package downloads.

For a new checkout, the upstream repository/version and FPGA sources are
pinned in `fpga/dependencies.lock.json` and `fpga/platform.lock.json`.
`fpga/scripts/fetch-deps.ps1` and `prepare-spinal.ps1 -Kind native` prepare the
driver; transfer that source to the board and build using
`fpga/software/spinal/build_native.sh` before building the game bridge.
`combat/board/fetch_mono.py` downloads the exact official ARMhf Mono packages
in `combat/board/mono.lock.json`, verifies hashes, and packages a private
runtime. Extract it into `/root/hackrpi`; no OS-wide Mono install is needed.
The current board uses Mono 5.18.1 and its original glibc 2.20.

## Validation and present limits

`combat/tests/board_remote_smoke.py` tests real Arduino samples -> managed
calibration -> control input -> game simulation -> identified FPGA frames,
and verifies focus loss pauses simulation. Run it with the game paused; it
does not take an active browser controller's lease. Keep the sensor steady
for this test. It leaves the game paused.

The accepted depth-read RTL measured **25.22 displayed FPS over 30.016 seconds
of uninterrupted active play**, with 757 acknowledged canvas updates, one
visible browser, fresh Arduino data throughout and 60.001 Hz simulation. The
GPU completion counter averaged 27.22 FPS and server collection 26.82 FPS.
The user accepted 25 FPS as sufficient. These are scene-dependent observations.
The game executable, native library, resolution and original visuals are unchanged.

The selected software includes unchanged-scenery projection caching, the
validated native compiler settings, and actual depth disabling for HUD draws
that do not use depth. The deployed library passed 360 queued comparisons
against 28 pre-change scene references with zero additional pixel differences.
The original CPU-vs-FPGA image mismatch remains unresolved. See the
[requirements audit](../reports/SOFTWARE_COMPLETION_AUDIT.md) and
[detailed software audit](../reports/SOFTWARE_PROFILE.md) for evidence and limits.
The direct-vertex-storage prototype was not selected after its combined-load test.

`render_fps` is a single-frame hardware timing, not displayed FPS. For controlled
comparisons, `FLIGHTING_CITY_XY_CACHE=0` disables the projection cache, and
`SPINAL_READBACK_BATCH=0` disables batch scheduling of the readback worker.
Metrics report `readback_policy=3` and `readback_policy_error=0` when that policy
is enabled successfully. The normal service selects both validated options.

Startup now restores the last commit's defaults: 320x240, scene 6, complexity
18, quality `low`, full neighbourhood range 1, and a 30 FPS rendering target.
The web producer has a 60 FPS pacing ceiling. These targets are not measured
performance claims. Simulation still uses the existing fixed 60 Hz clock with
bounded catch-up. The font-atlas HUD matches the original glyph rendering in
the tested CPU, serialized-FPGA and queued-FPGA cases.

The prepared pipeline is enabled, with pinned buffers, conservative rejection
of triangles that cannot cover a pixel sample, and cached flat colour writes.
256 FPGA frame comparisons found zero additional pixel differences, including
subpixel boundary cases and alternating buffers. The separate legacy
`SPINAL_BATCH_TEST` path remains disabled; the selected pipeline retains three
synchronization commands per triangle. `FLIGHTING_PIPELINE=0` selects the
legacy serialized loop for rollback.

The Arduino reader retains its original read size and timeout. It clears a
stalled data endpoint once; repeated PIPE failures permit one USB connection
reset per 30 seconds. This does not flash firmware. After publishing a complete
sample it now yields for up to 150 ms, matching the measured 5 Hz USB arrival
cadence. Partial next messages are drained immediately. Repeated paused-game
A/B/A trials retained every previously received sample while reducing USB
interrupts and roughly doubling completed FPS. That is not a displayed-FPS
claim. Twelve sensor tests and the 256-frame pixel gate passed with this change.
Set `HACKRPI_SENSOR_FRAME_YIELD_MS=0` when starting the service to reproduce the
original timing; the reader also accepts `--frame-yield-ms 0`.

This backend uses W16 depth, LEQUAL and reciprocal-W scaling 0.19 to avoid
severe Z16 quantization at long range. It does not exactly implement the
desktop reference's high-precision LESS depth. Seven original-profile frames
already differed by 167–979 pixels from the CPU reference, even after RGB565
quantization. Zero additional FPGA differences does not satisfy the user's
strict zero-error original-reference gate. Thin road/water layers retain
precision differences; the general graphics contract is not declared passed.

The accepted GPU2 image is `recovery/known-good-25fps/Spinal_Standard_GPU.sof`:
SHA256 `1af55209f870b807422caf18b2966a65745adcf6e22eef640f6de7b3260ab767`.
It pipelines eight ordered, uncached depth reads. Timing and all 342 compiled
signal-pin assignments passed the board gates. The complete restore point is
tag `de10-known-good-25fps`; the earlier image remains at `de10-known-good-16fps`.
See the [recovery guide](../../recovery/README.md). Reloading the saved image
after power loss does not require synthesis. Automatic power-on startup is
not configured; Linux/network/game startup is still required.
