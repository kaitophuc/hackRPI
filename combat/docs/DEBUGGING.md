# Debugging and reproducibility

## Classify before expanding the scene

| Class | First reduction |
| --- | --- |
| Gameplay | Replay identical tick-indexed inputs with rendering disabled; compare aircraft state |
| Geometry/camera | Capture clip vertices/camera; use colored triangle, cube, near-plane scene, and wireframe on software |
| Renderer/API | Reproduce exactly the same frame JSON through both backends; inspect depth, winding, UV origin, uploads and unsupported-state logs |
| FPGA integration | Run the smallest failing scene with the recorded RasterIX/hardware configuration; inspect bus/context/resource/format errors |
| Streaming | Compare GPU/readback output to the streamed image; measure encode/transport/browser display separately |

Keep resolution, seed, scene, tick and complexity fixed. Start with the smallest applicable diagnostic; terrain detail is not necessary to debug a reversed texture or a depth-state failure. Persist the classification in the captured `Category` field.

## Capture an exact frame

Press F5, or use:

```powershell
.\dist\FlightingSimulatorGame.exe --headless --scripted --ticks 90 --scene 4 --capture captures\texture --out captures\texture.ppm
.\dist\FlightingSimulatorGame.exe --render-capture captures\texture\frame.json --out captures\reproduced.ppm
```

The capture JSON contains contract/version, backend identity, seed, tick, aircraft state, effective input, camera eye/target/up, near/far/FOV/aspect, clear color, viewport, homogeneous clip-space vertices with RGB/UV, triangle indices, draw order, cull/depth/texture states, wireframe state and complete original texture pixels. All HUD triangles are included, freezing runtime telemetry text for exact frame reproduction. No external asset paths are required. `frame.ppm` is the reference image; `README.txt` describes its contents.

Captured geometry is the final CPU output, which isolates rasterization. The seeded world and input replay reproduce simulation/geometry preparation separately. A frame capture alone is not a full simulation checkpoint: reconstruct the preceding physical trajectory using its replay file.

Combat captures include player HP, combat tick, enemies, projectiles, bursts, cooldowns, score, wave and RNG state. Format 6 selects the endless run; format 5 retains repeating-map free flight, format 4 fixed Hanoi, format 3 earlier terrain/combat, and formats 1/2 combat-free flight. Captures embed runner distance/dodge velocity and frozen geometry. Headless `.run.txt` files contain distance, horizontal dodge velocity and vertical dodge velocity; `.combat.txt` contains tick, HP, kills, wave, actor counts, shot count, hits, game over and RNG. Compare all three state summaries when debugging replay or collision differences.

## Compare desktop and RasterIX/board output

Render the same captured frame through the native backend:

```powershell
.\dist\FlightingSimulatorGame.exe --backend rasterix --render-capture captures\texture\frame.json --out captures\rasterix.ppm
.\dist\FlightingSimulatorGame.exe --compare captures\texture\frame.ppm captures\rasterix.ppm --tolerance 8 --edge-radius 1 --allowed-fraction 0.01 --out captures\diff.ppm
```

The comparator reports mean/maximum center-pixel max-channel error and the fraction of unmatched pixels. It requires equal-size RGB8 P6 PPMs. For each pixel, both images must have a matching color within the chosen radius in the other image. The default 8-level/channel tolerance, one-pixel edge radius and 1% unmatched threshold are starting points, **not agreed board acceptance criteria**. Review RGB565/RGB444 and depth-format quantization with the GPU team. Inspect the red mismatch mask, especially around clipped silhouettes, shared triangle edges, texture boundaries and HUD alignment. A passing numeric threshold alone does not prove correctness.

Same-renderer reproduction should use tolerance=0, radius=0, fraction=0. Independent replay runs should use `--no-hud` for image identity; timing labels and LIVE/RECORD/REPLAY text differ between runs. Native interpolator precision and edge fill rules may differ from the double-precision software implementation.

Exit 0 means success, 1 means an invalid operation or failed backend, and 2 means image comparison exceeded the configured mismatch allowance. Error output goes to stderr; fatal errors also write `flighting-error.log`. Explicit negative resource/option tests intentionally emit errors while the self-test process still succeeds.

## Timing boundaries

| Counter | Measured boundary |
| --- | --- |
| Simulation | CPU time for fixed-step aircraft updates in the current rendered iteration; batch total in offline headless mode |
| Geometry preparation | CPU world mesh, camera projection, scene and HUD construction |
| Graphics submission | `IRenderer.Render`: CPU rasterization on software; marshaling, native submission, completion and readback on the native bridge |
| Platform delivery | Separate `IRenderer.Deliver` / `fg_present` callback; no-op on software; measured outside submission |
| Frame copy | Windows bitmap upload via LockBits/Marshal.Copy |
| Window paint | Graphics.DrawImage duration, measured separately from bitmap upload |
| Dropped wall time | Elapsed time intentionally discarded by bounded simulation catch-up |
| Triangles/draws | Submitted geometry, before clipping/culling; includes HUD geometry |
| Texture bytes | Logical active RGBA8 texels; excludes driver copies/alignment/depth/color buffers and native caches |

HUD telemetry shows the preceding completed frame's counters because HUD geometry is prepared before current submission. Headless console counters describe the final frame. Individual headless timings include startup/JIT effects and are not benchmark claims.

The native ABI has a blocking `fg_end` completion/readback boundary and a separate `fg_present` delivery boundary. It cannot isolate GPU execution from readback inside `fg_end`; the GPU host must instrument those internal stages and its streamer/encoder/transport separately. Windows delivery telemetry adds bitmap copy time to any platform delivery time; paint is tracked separately. Windows paint completion does not prove a monitor scanout; browser displayed FPS does not measure GPU rendering FPS. There is no browser/GPU FPS label in this project.

## Fixed-step and input checks

`--self-test` covers bounded catch-up and discarded time, paused accumulator reset, seeded terrain, record/replay state identity, varying render cadence, sequence/timestamp rejection, NaN/unknown button rejection, watchdog neutralization, focus-loss clearing, bank direction, button effects, depth ordering, winding, near/eye clipping, UV corners, texture sampling, HUD ordering and complete capture reproduction for every scene. `--desktop-smoke` exercises the real WinForms host's key mapping, focus loss, explicit resume, single step, bitmap upload and window painting into a PNG without opening a game window.

These automated host tests are not evidence of interactive flight testing, a physical focus change, ARM behavior, GPU compatibility, FPGA frame rate or browser streaming. Follow the validation matrix and record those results separately.
