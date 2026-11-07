# Endless-run scenery and rendering cost

New games use an automatic forward run with a fixed camera. One cached **1760 × 1980 metre** Hanoi sequence is split into nine **220 metre** sections. A fixed **11-slot** pool scrolls these sections past the plane and reuses them ahead; side-to-side free-roam tile copies are not submitted. Distance grows separately while the plane and combat actors stay near the camera. Ground queries share the scrolling phase, and source meshes are generated once per detail variant.

The plane models, calibration, shooting, enemy AI, health, scoring, 60 Hz simulation and default 640 × 400 framebuffer remain. Tilt now dodges horizontally/vertically within the fixed view; the plane cannot turn the forward route. Large diagnostic panels are omitted from the playable dodge area.

## Current endless-run measurements

At route distances 0, 495, 990 and 1485 metres, the current fixed-camera run measured **17.67, 12.69, 5.89 and 10.67 ms** per frame (mean of pose medians **11.73 ms**). Same CPU renderer, resolution, complexity and sampling method as below. These route views differ from the previous free-flight views, so this is a current measurement, not a direct percentage comparison. Raw results are in `tests/endless-performance-results.json`.

## Changes that reduce work

- Cache the terrain and city meshes once per detail variant instead of generating a moving ground grid every frame.
- Share identical vertices, split the river into smaller culling chunks, and submit only camera-visible neighboring sections.
- Draw opaque chunks near to far so existing depth rejects hidden fragments earlier.
- Reuse software clipping buffers and per-vertex screen coordinates; avoid wireframe calculations during normal play.
- Restrict large triangles to conservative scanline spans and pack constant palette colors once per triangle. Exact edge, depth, gradient and texture behavior is retained.
- Limit redraws to 5 Hz while paused and 2 Hz while unfocused. Active rendering is capped at 60 Hz; simulation remains fixed at 60 Hz and independent of rendering.

## Earlier renderer optimization comparison

Windows, installed .NET Framework 4.x, **CPU software renderer**, 640 × 400, complexity 18, HUD disabled. Each of four camera poses was warmed up for four frames, then measured for 25 frames. Entries are median full frame costs at that pose, including scene preparation and rendering.

| View | Before | After |
| --- | ---: | ---: |
| Starting city approach | 39.14 ms | 19.77 ms |
| Lake / quarter turn | 31.05 ms | 15.33 ms |
| River-side heading | 36.92 ms | 10.73 ms |
| Reverse heading | 32.64 ms | 18.81 ms |
| Mean of these medians | **34.94 ms** | **16.16 ms** |

That is **53.8% less frame time** in this comparison, with **44.5% fewer submitted vertices** and **11.2% fewer triangles** across the four views. Timings vary with camera position and system load. These measurements compare the original fixed-map build with the optimized repeating-map build. They measure CPU rendering cost; GPU electrical power, RasterIX and FPGA performance were not measured.

The captured results are in [`tests/performance-results.json`](../tests/performance-results.json). Close the game, then measure the current build without opening a game window by running from `hackRPI`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File combat/tests/benchmark.ps1
```

## Verification

- 363 core checks, including the 11-slot pool over 80 section boundaries, fixed camera/corridor bounds, continuous scrolling, restart, sensor dodge mapping and legacy modes.
- Seven frozen original scene captures reproduced byte for byte by the optimized renderer.
- Ninety-six varied flat, gradient, textured, clipped and wireframe triangle frames matched the original renderer byte for byte.
- Full combat/replay/desktop suite: the endless-run 1200-tick fire/dodge example ends with 4 kills and 35 HP; idle aircraft reaches game over at tick 1257. A straight-flight comparison preserves legacy damage, kills, cooldown and RNG behavior under the frame conversion.
- Live COM3 accelerometer: calibration button, advancing combat, enemy spawning, firing and focus safety pass.

New recordings use format 6 for the endless run. Formats 1–5 retain their original movement and environments. Captures embed runner state and complete frame geometry, and reproduce independently of map generation.
