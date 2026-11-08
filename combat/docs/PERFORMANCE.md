# 320x240 performance profile

The game defaults to **320x240**, low-detail geometry and **30 FPS rendering**. Simulation, sensor processing and combat remain fixed at **60 Hz**. The 11-slot endless route still recycles nine cached sections of one Hanoi sequence. The Windows game runs with the same controls, calibration button, scoring, enemies, collision rules and replay format.

## Work reduced

- Simplify ground patches, roads, bridge sleepers, truss beams and circular landmark details. Keep the Hanoi landmarks, roof shapes and color palette. In the fixed-camera runner, omit building faces the camera cannot see. Legacy free-flight modes keep their existing meshes.
- Cache simplified player/enemy meshes. Enemies beyond 100 metres use a smaller silhouette mesh; close enemies retain canopy, propeller and painted wing markings. Cull invisible enemies, shots and bursts before transforming them.
- Use one camera-facing quad per tracer and four burst spokes. Projectile movement, hit detection and damage are unchanged.
- Reuse frame, draw, vertex and index buffers. Compile the pixel font once, combine matching glyph runs vertically and share the four vertices of each HUD rectangle. A compact 320x240 HUD keeps health, kills, enemy markers, aiming, distance and the clickable Replay action readable.
- Keep gameplay at five or fewer draw batches. The native framebuffer has **70% fewer pixels** than 640x400. Rendering runs at 30 FPS, paused rendering at 5 FPS and unfocused rendering at 2 FPS. A deadline scheduler avoids drifting to 20 FPS on a 16 ms desktop timer; slow frames do not trigger render catch-up bursts.

## Measurements on this PC

Windows, installed .NET Framework, **CPU software renderer**, seed 1337, complexity 18. Each of four route phases received four warmup renders and 25 measured renders; entries are pose medians. HUD and active combat actors are excluded from the first comparison.

| Route distance | Previous 640x400 full | New 320x240 low | Triangles before -> after |
| --- | ---: | ---: | ---: |
| 0 m | 17.70 ms | 4.61 ms | 15,178 -> 4,443 |
| 495 m | 12.64 ms | 4.05 ms | 9,374 -> 3,953 |
| 990 m | 5.91 ms | 1.22 ms | 4,902 -> 565 |
| 1485 m | 10.66 ms | 2.38 ms | 11,712 -> 2,858 |
| Mean of pose medians | **11.73 ms** | **3.06 ms** | **71.3% fewer triangles** |

The combined default changes reduce measured CPU frame time by about **74%**. At the **same 320x240 resolution**, low detail submits **70.4% fewer triangles** than full detail, separating geometry savings from resolution savings. With the compact HUD enabled, the four low-profile poses measured **5.15, 4.59, 1.77 and 2.98 ms**. These are PC timings, not FPGA timings or power measurements.

Raw baseline, full/low equal-resolution and HUD results are in [low-power-performance-results.json](../tests/low-power-performance-results.json). Full-detail 640x400 route images still match the four pre-change reference images byte for byte. Earlier optimization evidence remains in [performance-results.json](../tests/performance-results.json) and [endless-performance-results.json](../tests/endless-performance-results.json).

Run from `hackRPI` with the game closed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File combat/tests/benchmark.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File combat/tests/benchmark.ps1 -Quality full -Width 320 -Height 240 -OutputDirectory combat/captures/performance/full
powershell -NoProfile -ExecutionPolicy Bypass -File combat/tests/benchmark.ps1 -Hud -OutputDirectory combat/captures/performance/hud
```

The benchmark writes four PPM images and `results.json`; timings vary with system load.

## Play and compare

```powershell
python play_combat.py --serial COM3
python play_combat.py --serial COM3 --quality full --fps 60
```

Both launch at 320x240 and use the existing USB bridge. Direct desktop options also support `--width 640 --height 400 --quality full --fps 60`. Quality changes only rendering; rendering cadence cannot change the deterministic simulation.

## Verification

- 421 core checks cover 320x240 corridor corners, profile-independent gameplay, native HUD hit bounds, frame pacing, complete-route buffer/cache reuse and legacy recordings.
- A busy scene with four fighters, 192 projectiles and 16 bursts stays below 9,000 triangles including HUD over 36 route phases, with at most five batches. This is a tested scene budget, not a hard limit that drops gameplay actors.
- Full executable validation covers capture reproduction, combat, keyboard/mouse input, letterboxed Replay clicks, record/replay identity and the real UDP watchdog. With the original enemy firing rate and half-speed enemy bullets, the 1,200-tick fire/dodge example ends at 4 kills and 100 HP; idle flight reaches game over at tick 3972.
- Live COM3/MMA7660 calibration, firing, advancing endless-run ticks, visible PLAYING feedback and focus safety pass at 320x240.

Recordings remain format 6; formats 1-5 keep their previous environments and controls. Captures serialize complete geometry synchronously. `Session.LastFrame` and its geometry are reusable buffers valid until the next render; serialize a capture before retaining it across renders.
