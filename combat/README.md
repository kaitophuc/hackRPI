# Flighting Simulator Game

## Arduino tilt controls in hackRPI

From the parent `hackRPI` folder, run `python play_combat.py` or double-click `Start Combat.cmd`. This builds the game locally and connects it to the existing Python USB bridge. No files from the original Temp directory are needed.

In the game, hold the MMA7660 in your normal grip and click the large **CALIBRATE & PLAY** button at the top. After 1.8 seconds, **PLAYING** starts automatic forward flight and enemy waves. Tilt left/right and up/down to move within the fixed-camera corridor. Normal grip stops lateral/vertical motion and levels the visual bank. **C** is an optional calibration shortcut. Coarse/noisy readings and normal hand movement do not reject calibration. The status bar includes horizontal/vertical reversal buttons. **F / left mouse** fires. Sensor loss pauses progress and clears firing; reconnect and calibrate again to continue. **P** resumes after switching windows without recalibrating.

To run the sensor mode directly while `python server.py` is already running:

```powershell
.\dist\FlightingSimulatorGame.exe --accelerometer http://127.0.0.1:8765/
```

The desktop adapter polls the local `/api/status` endpoint in a background thread. It uses all three acceleration axes to calibrate the gravity direction. Samples are normalized, centered with component medians, and the nearest 70% are averaged to reduce outliers. Calibration requires five distinct fresh samples. Filtered tilt becomes an analog dodge command; pose/bank is visual and never steers the route. Keyboard/mouse firing stays local to the focused window. No Arduino firmware changes are made. Without `--accelerometer`, WASD/arrow keys control the same endless run.

To verify real hardware, run `python server.py`, leave the sensor still, and run `powershell -NoProfile -ExecutionPolicy Bypass -File combat/tests/sensor-smoke.ps1 -Desktop` from `hackRPI`. This checks actual USB/HTTP/C# samples, calibration, combat firing and focus safety, then saves the sensor-enabled desktop preview under `combat/captures/validation/`.

A runnable desktop flight-development lab with seven diagnostic scenes, a portable fixed-step simulation, and a selectable native RasterIX bridge interface. The graphics/input contract is **proposed**, awaiting GPU-team approval. The bundled desktop renderer is an original CPU software rasterizer; it is not RasterIX and makes no FPGA performance claim.

## Build and run on Windows

Build from source after cloning the repository, then open the game from this directory:

```powershell
.\build.cmd
.\dist\FlightingSimulatorGame.exe
```

Requires Windows with .NET Framework 4.x (tested using the installed Framework compiler/runtime). No asset downloads, Python packages, FPGA, or network access are needed for keyboard play. Render resolution defaults to 320×240 and is scaled into a resizable window. `--width` and `--height` change the internal resolution; `--complexity 4..48` selects cached scenery detail and view distance (or the terrain grid size for legacy recordings). The window preserves the framebuffer aspect ratio. Build output and generated captures stay local and are excluded from Git.

| Control | Action |
| --- | --- |
| Up / Down or W / S | Dodge upward / downward |
| Left / Right or A / D | Dodge left / right |
| Page Up / Page Down | Increase / decrease automatic forward speed |
| Space / Shift | Airbrake / boost |
| F / left mouse button | Hold to fire; release to stop |
| Replay button / Enter | Start a fresh round after game over |
| 1–7 | Select diagnostic scene; scene 6 is the playable flight loop |
| P | Pause / resume; explicitly resume after focus loss |
| N | Advance one simulation tick while paused |
| F2 | Software geometry wireframe |
| F5 | Save a complete frame reproduction bundle under `captures/` |
| R | Reset aircraft (disabled while recording or replaying) |
| Esc | Quit |

Focus loss clears axes/buttons and throttle, discards accumulated simulation time, and pauses. Reacquiring focus requires P to resume. Replays also pause on desktop focus loss. A disconnected or timed-out platform input source pauses automatically and resumes only when valid input returns. The throttle remains zero after local focus loss until Page Up is pressed.

New games use a fixed camera and automatic forward progression. The plane remains at a constant depth and can dodge horizontally and vertically within the view. Input combinations are normalized; releasing input smoothly stops dodge velocity. Visual bank and pitch follow the dodge, while heading remains forward. Scenery, enemies and projectiles scroll together past the anchored plane. The player never needs to turn around. Older replays retain their original free-flight controls.

## Combat

Scene 6 runs an endless forward-flight combat game. The player starts with **100 HP**. Gray WWII-style enemy fighters with red markings approach in waves, aim at the current flight path, and fire visible red/orange projectiles. Each incoming hit deals **5–10 HP** of damage. Dodge sideways or vertically; bullets do not home after being fired. At most four enemy fighters are active at once.

Enemies use their original firing rate: about **1.4–1.9 seconds between shots**, with staggered first shots. Enemy bullets travel at **half their original speed**; player bullet speed and firing rate are unchanged.

Hold **F or the left mouse button** to fire golden tracers along the nose/aim marker. A single hit destroys an enemy, produces a brief hit burst and adds one kill. Fire is rate-limited with unlimited ammunition. Player and enemy shots use swept collision to avoid tunneling through an aircraft between fixed ticks. Player collision is intentionally forgiving; there is no ramming damage.

The HUD shows health, kills, hostiles and distance travelled. At zero HP, flight, scenery and combat stop. Click **REPLAY** or press **Enter** to restore 100 HP, reset distance/scenery, clear actors and begin a new round. The replay button handles the scaled/letterboxed viewport. During recording it starts a fresh recording file; recorded playback restarts at tick zero.

Diagnostics 1–5 and 7 remain isolated from combat. Pausing or losing focus also stops combat, and focus loss clears held fire. Enemy variants reuse cached local-space aircraft geometry with a different paint scheme, within the existing opaque triangle feature set.

`tests/combat-flight.csv` is a deterministic 1200-tick shooting/dodging example:

```powershell
.\dist\FlightingSimulatorGame.exe --replay tests\combat-flight.csv
```

## Hanoi setting

The default performance profile renders at **320×240 and 30 FPS** while simulation and control processing stay at **60 Hz**. Low-detail city and aircraft meshes preserve the setting, plane silhouette, palette and combat rules. The HUD uses native pixel text at this resolution. `--quality full` restores detailed geometry; `--fps 60` raises the render cap. The Windows version supports both profiles. For the earlier desktop presentation, use `--quality full --width 640 --height 400 --fps 60`. See [PERFORMANCE.md](docs/PERFORMANCE.md) for measurements.

The default flight scene now flies over a simple **Hanoi-inspired city, circa 1972**: tiled-roof Old Quarter neighbourhoods, Hoan Kiem Lake with Turtle Tower, Ngoc Son Temple and the red The Huc footbridge, and Long Bien's railway trusses across the Red River. A few street shelters, damaged roofs and rail-side crater marks suggest the wartime period. Distances and architecture are compressed for gameplay; this is not an exact historical reconstruction.

The existing plane models, city palette and combat remain. The fixed-camera corridor replaces free roaming. Buildings remain scenery, with no new building-collision damage. `--complexity` changes house density and view distance. See [HANOI_SCENERY.md](docs/HANOI_SCENERY.md).

New games build one **1760 × 1980 metre** Hanoi sequence, divide it into nine **220 metre** sections and reuse them in a fixed 11-slot pool. Sections pass behind the camera and recycle ahead. Only one forward route is active; no neighboring free-roam map is generated. Plane, enemy and bullet positions stay near the camera while distance accumulates separately. Cached indexed meshes, culling and the optimized renderer are retained. Paused/unfocused redraws remain 5/2 Hz; active simulation remains 60 Hz. See [PERFORMANCE.md](docs/PERFORMANCE.md).

## Build and validate

`build.cmd` compiles the original C# source using the Windows .NET Framework compiler; it needs no NuGet packages or additional SDK:

```powershell
.\build.cmd test
.\dist\FlightingSimulatorGame.exe --desktop-smoke --out captures\desktop-preview.png
.\dist\FlightingSimulatorGame.exe --suite --capture captures\suite
```

For the additional executable-level record/replay, capture and real UDP watchdog tests, run `python tests/validate.py` if Python is installed. The game itself does not require Python.

An optional `build.ps1 -Test` is included for machines that permit PowerShell scripts. The supplied `build.cmd` works without changing PowerShell execution policy. Do not change system security settings to build this project.

For Linux/ARM and the RasterIX bridge, see [ARM.md](docs/ARM.md). A modern .NET headless project is included, but this environment did not have that SDK, an ARM toolchain, or RasterIX.

## Deterministic record and replay

```powershell
.\dist\FlightingSimulatorGame.exe --headless --scripted --ticks 600 --record tests\example.csv --no-hud --out captures\recorded.ppm
.\dist\FlightingSimulatorGame.exe --headless --replay tests\example.csv --no-hud --out captures\replayed.ppm
.\dist\FlightingSimulatorGame.exe --compare captures\recorded.ppm captures\replayed.ppm --tolerance 0 --edge-radius 0 --allowed-fraction 0 --out captures\replay-diff.ppm
```

`--record` also works in the desktop window. Each file starts at the standard initial aircraft state, includes world seed and 60 Hz version metadata, and records the effective controls for every executed tick. Pauses and discarded wall time are not physical simulation ticks. R reset is disabled during record/replay; the game-over Replay action explicitly starts a new round/recording or rewinds playback. Replay ends at EOF or game over; it never invents further controls. `tests/sample-flight.csv` is a delivered 600-tick example. Headless runs write aircraft state to `<output>.state.txt` and a deterministic combat summary to `<output>.combat.txt`.

New recordings use format 6 and include endless-run controls, distance/scenery progression and seeded combat. Format 5 retains the previous repeating-map free flight; format 4 retains fixed Hanoi; format 3 retains earlier terrain and combat; formats 1/2 retain combat-free flight. Record and replay with the same scene selection. Rendering cadence does not change simulation decisions. Headless `.run.txt` output records distance and dodge velocity alongside aircraft/combat state; captures embed runner state and frozen frame geometry.

Rendering cadence does not affect a replay's simulation trajectory. Floating-point results across different architectures are compared with a documented numerical tolerance, rather than promising bitwise cross-architecture identity. Disable the live HUD for image comparisons between separate simulation runs: its status and timings intentionally differ. Capturing a frame freezes the HUD geometry, so reproducing that captured frame is exact on the same renderer.

## Diagnostic scenes

| Key | Scene | Inspection |
| --- | --- | --- |
| 1 | Colored triangle | Red lower left, green lower right, blue top; CCW front face |
| 2 | Overlapping triangles | Near orange triangle remains visible although far cyan is submitted later |
| 3 | Rotating cube | Six colored faces; camera projection, winding and clipping |
| 4 | Textured cube | Nearest/clamped procedural checker; red top left, green top right, blue bottom left, yellow bottom right in texture space |
| 5 | Near-plane crossing | Triangle moves through the near plane and behind the eye as simulation ticks advance |
| 6 | Small terrain and aircraft | Seeded low-poly terrain, reference path and controllable chase-camera aircraft |
| 7 | Minimal HUD | Opaque overlay drawn over a depth-tested triangle, with explicit screen-axis labels |

The identical scene builder feeds every backend. Use the same seed, tick, resolution and complexity on the desktop and board. Camera-space geometry is transformed on the CPU into homogeneous clip coordinates; each backend performs clipping/rasterization against those coordinates.

## Backend selection and evidence

```powershell
.\dist\FlightingSimulatorGame.exe --backend software
.\dist\FlightingSimulatorGame.exe --backend rasterix --scene 4
```

The RasterIX selection loads `flighting_rasterix_bridge.dll` (or `libflighting_rasterix_bridge.so` on Linux). Without the GPU-team host implementation, it fails explicitly. The original `native/gl_bridge.c` maps the proposed subset into fixed-function GL calls; the GPU team must supply context, symbol resolution and frame delivery hooks for its selected RasterIX software or FPGA path. It is source for integration, not a verified RasterIX build. No fallback or simulated board result is substituted.

[CONTRACT.md](docs/CONTRACT.md) specifies feature limits and input packets. [VALIDATION.md](docs/VALIDATION.md) records actual evidence and all pending hardware work. [DEBUGGING.md](docs/DEBUGGING.md) documents captures, timing boundaries, comparison tolerance and bug classification.

## Project map

- `src/`: simulation, platform input state, diagnostics, software renderer, RasterIX adapter, capture tools, tests and Windows host.
- `native/`: versioned C ABI, GL glue and CMake integration target.
- `assets/`: original asset license and input JSON schema. Checker texture, pixel font and aircraft geometry are generated from source.
- `docs/`: proposed contracts, ARM instructions, debugging workflow and validation record.
- `tests/sample-flight.csv`: deterministic flight recording.
- `dist/FlightingSimulatorGame.exe`: built Windows development executable.
- `captures/desktop-preview.png`: desktop host smoke-test preview.

## Limits

Flight is an arcade kinematic model, not an aerodynamic training simulator. Ground contact raises the aircraft to terrain clearance and nudges it upward. The low-detail Hanoi city and seeded countryside are not a surveyed terrain model or a terrain-streaming system. Rendering is opaque, single-texture, triangle-only; there are no shaders, blending, mipmaps, lighting, fog, transparency, audio or imported assets. Wireframe is desktop-only. Logical resource counters exclude native driver allocation overhead. Frame copy, OS paint, browser delivery, and GPU execution are different measurements.

GPU-team agreement, a concrete RasterIX context host, ARM execution, RTL runs, FPGA tests, browser-input integration and streaming measurements remain pending. See the validation matrix before drawing compatibility conclusions.
