# Validation record

Recorded 2026-11-07. Environment: Windows, installed .NET Framework 4.x compiler/runtime, AnyCPU managed EXE, software renderer. This is an initial development deliverable. GPU-team agreement has not occurred.

## Completed evidence

| Item | Desktop software / host | RasterIX software / RTL | FPGA / ARM board |
| --- | --- | --- | --- |
| Windows executable build | PASS, `build.cmd` | Not applicable | Not built |
| Seven diagnostic scenes | PASS, rendered/captured; all seven capture roundtrips checked | Untested | Untested |
| Colored triangle / orientation | Automated draw/cull tests and capture | Untested | Untested |
| Overlap / depth | PASS, near-first and far-first submission | Untested | Untested |
| Rotating cube / camera | Scene rendered, winding tested | Untested | Untested |
| Texture upload / UV origin | PASS, quadrant/sample tests, 1024-byte texture counter, invalid upload rejection | Untested | Untested |
| Near/eye clipping | PASS, crossing, wholly clipped, and negative-w cases | Untested | Untested |
| Terrain / aircraft flight | PASS, deterministic 600-tick scripted path | Untested | Untested |
| HUD ordering / screen coordinates | PASS, depth-disabled overlay plus scene 7 | Untested | Untested |
| Input sequences/timestamps/sessions | PASS, gate tests including delayed timestamps and watchdog | Adapter entry point only | Browser service unavailable |
| UDP adapter integration | PASS, real loopback packets, timeout pause and fresh-input resume to 60 ticks | Not connected | Not connected |
| Fixed dt / bounded catch-up | PASS, dropped-time accounting and pause reset | Shared portable source only | Untested |
| Seeded world and replay | PASS, identical aircraft state with variable render cadence | Untested | Untested |
| Record/replay image identity | PASS, 600 ticks, no HUD, identical image/state SHA256 | Untested | Untested |
| Full frame capture reproduction | PASS, all scenes in self-tests; independent CLI reproduction | Untested | Untested |
| Comparison tool | PASS, exact desktop comparison | Cross-backend tolerance unapproved | Untested |
| Wireframe | PASS, software debug rendering | Explicitly unsupported in bridge | Untested |
| Desktop key/focus/pause/step | PASS, actual host methods/events and window paint exercised by smoke test | Not applicable | Untested |
| Combat HP / shooting / one-hit enemies | PASS, 100 HP, 5–10 incoming damage, swept hit/near-miss/first-hit tests, cooldown and bullet expiry | Untested | Untested |
| Game over / play again | PASS, zero-HP freeze; actual rendered button clicked in letterboxed host; Enter restart; recording reset | Untested | Untested |
| Combat input replay | PASS, HP/kills/projectiles/waves/RNG/flight summary identity | Untested | Untested |
| Survival / shooting example | PASS, 1200 ticks, 4 kills, 35 HP; repeatable | Untested | Untested |
| Idle aircraft under enemy fire | PASS, 100 HP exhausted; game over at tick 1257 | Untested | Untested |
| Hanoi scenery | PASS, seeded geometry cache, density levels, lake/river height queries, unchanged countryside and city frame reproduction | Untested | Untested |
| Hanoi / legacy replay environments | PASS, format 6 is an endless run; format 5 keeps looping free flight; formats 1-4 retain earlier environments | Untested | Untested |
| Endless run / fixed section pool | PASS, fixed camera, bounded dodge, nine source sections, 11 recycled slots across 80 section boundaries, consistent scrolling collision frame | Untested | Untested |
| Renderer optimization equivalence | PASS, seven original captures plus 96 varied triangle frames match byte for byte | Untested | Untested |
| CPU frame cost | PASS, endless route mean 11.73 ms; historical renderer comparison 34.94 to 16.16 ms; see PERFORMANCE.md | Not measured | Not measured |
| Live Arduino / calibration button | PASS, COM3/MMA7660, HTTP to C# calibration, moving combat, firing and focus safety | Not applicable | Not applicable |
| Missing native backend | PASS, explicit failure, no software fallback | Bridge unavailable | Bridge unavailable |
| Native C bridge source | Supplied, not compiled here (no native toolchain) | Requires GPU-team host/context | Requires GPU-team host/context |
| ARM host / .NET project | Source/build instructions supplied; SDK unavailable here | Not built | Not built |
| Native frame delivery / streaming | Separate timing boundary defined | Not exercised | Not measured |
| Interactive human flight session | Not performed | Not performed | Not performed |

The core self-test executable passes **363 checks**. Coverage includes flight/rendering/combat, noisy accelerometer calibration, deterministic cached scenery, periodic ground/water, seam continuity, bounded cache size, actor continuity, adjustable density and environment selection. The desktop smoke test exercises keyboard/mouse firing, release/focus safety, game over, letterboxed replay-button hit testing and Enter restart. `tests/validate.py` additionally runs black-box executable checks, 600-tick image/state/combat identity, old/new replay environment selection, the repeatable 1200-tick shooting/dodging flight, actual idle death under enemy fire, wireframe, expected error paths and real UDP timeout/resume. The optimized renderer reproduced seven original scene captures and 96 varied triangle frames byte for byte. See `tests/validation-results.json` for executable/replay checksums and final aircraft/combat state, and `tests/endless-performance-results.json` for current timing evidence. Expected negative tests print resource/unsupported errors intentionally.

`captures/suite/` contains one frame bundle for each diagnostic. Scenes use tick 90 except scene 5, which uses tick 15 to capture a visible near-plane crossing. Each scene restarts from the standard initial aircraft state with seed 1337. Captures and smoke screenshots are supplied for inspection; they are not board evidence.

## Re-run

```powershell
.\build.cmd test
python tests\validate.py
.\dist\FlightingSimulatorGame.exe --suite --capture captures\suite
```

Python is optional for black-box orchestration; the EXE's built-in tests and game do not require it. Validation writes new captures/replay files beneath the project or OS temporary directory. A failed assertion or process returns nonzero. Socket restrictions are reported as UNTESTED, never a pass; loopback sockets worked in the recorded run.

## Pending acceptance

The proposed graphics/input contract needs review and sign-off from the GPU/platform team. Select an exact RasterIX commit, software configuration and ARM target, implement the native host hooks, compile the bridge, and run the same suite/replay/captures. An RTL test harness is not included because no selected RTL interface/build or GPU-team environment was supplied. No Windows OpenGL, RasterIX, RTL, FPGA rate or browser-stream compatibility claim is implied by software-rendered output.

Frame delivery, GPU execution, readback and streaming must be measured independently in the platform host. The desktop CPU timing boundary is implemented, but observed one-frame timings are not reliable benchmark figures. Quantization/edge tolerances, acceptable aircraft-state numerical drift and target resolution/complexity/frame rate remain to be agreed.
