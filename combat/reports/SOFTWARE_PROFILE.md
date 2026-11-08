# Software performance and fidelity audit — 2026-11-08

Reference commit: `6b55fee2fd837894c211b46652201583ec096488`.

Current checkpoint: the later depth-read RTL measured **25.22 displayed FPS**
with this same selected software and was accepted at 25 FPS. The software-only
measurements below are historical. See the [recovery guide](../../recovery/README.md)
and [RTL evidence](../../fpga/experiments/rtl_profile/README.md).

This pass keeps 320×240 RGB565 and the accepted 50 MHz FPGA image. It restores
the commit's scenery profile: scene 6, complexity 18, quality `low` (the commit's
default), seed 1337, neighbourhood range 1. The earlier board profile and isolated
24–32 FPS samples used complexity 4 and range 0.55; those are not representative
of the restored game's complete workload.

The latest selected software bypasses depth reads for HUD draws that do not
use depth. Its controlled moving-game test reached **21.70 completed FPS**;
the latest complete visible-browser measurement is **16.27 FPS over 30.98
seconds** with the Arduino fresh throughout. The selected build passed 360 queued
frame comparisons against 28 pre-change scene references with zero additional
pixel differences. The **27 FPS minimum remains unmet**, and the existing
original CPU-reference mismatch is still unresolved.

## Reference and rollback

`build/software-profile/reference-manifest.json` identifies the commit and SHA256
of the pre-change source archive and diff. The archive is under
`build/software-profile/rollback-20261107-234135/`. On the board, the prior executable
and native library are retained in `/root/hackrpi/rollback/software-profile/`.
The earlier complete pre-pipeline rollback also remains available.

Seven deterministic moving-game checkpoints (ticks 2, 90, 180, 360, 600, 900,
1200) have identical geometry and CPU-rendered image hashes between the commit
and the current source with the original scenery settings. Physics, combat,
animation poses and scenery generation are not approximated or simplified.

## What profiling established

- The suspected per-frame draw-cache leak was **not reproduced**: the moving
  workload reuses five draw objects. Blocking garbage collection took about
  22 ms, with another 54 ms of concurrent collection in a 15-second preparation
  run, so it was not the principal bottleneck.
- On the ARM CPU, original-profile scene construction took about 16 ms in the
  isolated moving sample. Initial triangle preparation took about 33 ms:
  roughly 10 ms managed validation, 5 ms packing, 18 ms native preparation.
- Reusable pinned arrays, native validation, projected-vertex reuse, inline
  clamps and finite/outcode checks reduced preparation to about 16 ms. Native
  code still checks all indices and input values before any GPU submission.
- A second CPU sample identified `List<Vertex>.Enumerator.MoveNext`, city
  assembly and camera projection as significant managed costs. Immutable chunk
  arrays and scalar projection reduced the same isolated ARM geometry sample's
  median from 15.77 to 11.10 ms. All seven original geometry and CPU-image
  hashes remained identical. Full-pipeline timings below use another workload
  and include contention; these isolated timings are not its frame latency.
- A 3-second software CPU-clock sample of the live game collected 2672 user-space
  samples: 45.43% were in Glide `_trisetup` (triangle setup and MMIO writes),
  9.24% in framebuffer copying. This does not distinguish arithmetic from bus
  backpressure and does not establish an RTL defect.
- Fixed-colour register and constant-combiner prototypes passed sampled image
  comparisons but did not offer a useful throughput gain. Their production
  hooks were removed. A flat-gradient shortcut produced four differing pixels
  in the 256-frame test and was rejected and removed.
- Two thread-affinity arrangements reduced controlled throughput; default
  scheduling is retained. USB polling, read-size and per-read-yield prototypes did not
  demonstrate a repeatable gain while retaining samples. Normal 512-byte,
  200-ms-timeout reads remain unchanged. Arduino firmware is unchanged.
- Grouping the three synchronization MMIO writes between one ARM barrier pair
  passed the initial 168-frame pixel sample but did not improve the A/B/A
  moving-game benchmark: 16.17 FPS before, 15.84 grouped, 16.00 after. Owner CPU
  time remained about 47.2 ms. The candidate was rejected, its production hook
  removed, and the exact prior native binary restored. This initial gate used
  the older 168-frame harness; it is not the expanded 256-frame validation.
- A tighter half-integer-only coverage candidate failed the expanded 288-frame
  gate with seven pixel differences. A focused 200-repeat checkpoint test
  produced 94 differences with three sync commands and 178 with four, all at
  pixel (289,158); the original conservative rule passed that 268-frame focused
  run with zero differences. The candidate and its production flag were removed,
  and the exact prior native library restored. The mechanism is unresolved;
  adding synchronization did not establish a fix. No performance claim is made
  for this rejected candidate.

## Retained software changes

- Bounded, pinned vertex/index buffers avoid per-frame index-array allocations
  and repeated managed vertex conversion. Native conversion retains the old
  float rounding exactly; there is no lower-precision rendering mode.
- Indexed vertices share clip codes and projected values. The clipping and
  projection arithmetic of surviving vertices is preserved.
- Immutable city chunk arrays avoid list-enumerator overhead; scalar camera
  and fighter projection retain the original arithmetic and vertex order.
- Cached XY dot-product prefixes reuse the unchanged parts of the endless
  camera's scenery transform. The remaining Z terms and projection operations
  retain their original order. Keys compare the relevant camera values and X
  offset bitwise; each immutable chunk owns at most one prefix array.
- Flat RGB register writes with identical float bit patterns are cached within
  a draw and invalidated at state changes and varying-colour triangles.
- Conservative rejection removes tiny triangles only when a superset of the
  accepted core's pixel sample positions contains no point inside their fixed
  coordinates. It includes boundaries, tests both integer and half-integer
  centers, and retains uncertain/large/degenerate cases. Visible detail and the
  framebuffer resolution are unchanged.
- Linux inotify wakes the server on atomic frame-file publication. Other files,
  such as sensor snapshots, do not trigger frame delivery. Portable polling is
  retained when inotify is unavailable. Pixel packets and ACK ownership remain
  unchanged.
- The font-atlas HUD is retained after exact comparisons against the original
  glyph geometry, including running, paused, calibration, damage and game-over
  states. The FPGA still draws every HUD pixel.
- The USB reader clears a stalled endpoint once before reconnecting. Persistent
  PIPE failures permit a USB connection reset at most once per 30 seconds,
  including failed reset attempts. Ordinary timeouts, malformed input and
  disconnects do not trigger resets. No firmware is flashed or FPGA reset.
- After publishing a complete sensor sample, the reader gives the USB host up
  to 150 ms of quiet time for the measured 5 Hz USB arrival cadence. It drains
  partial next messages immediately, retains original transfer size/timeout,
  and cancels the wait on shutdown. The real stream retained the same sample
  rate while USB interrupts fell substantially in repeated A/B/A tests.

## Validation gates

- 428 portable C# checks and 429 Windows desktop checks passed with the XY cache
  enabled, including exact projection comparisons across 2000 points.
- Twelve sensor framing/freshness/control/recovery checks passed on the computer,
  including publication before yielding and immediate draining of a partial next
  message.
- Four frame-publication tests passed on the board, including notification
  filtering, descriptor release and immutable snapshots across atomic renames.
- **256 FPGA comparisons: zero differing pixels** against serialized FPGA
  rendering, including seven original-profile game checkpoints, seven diagnostic
  scenes, 1024 generated subpixel/clip/colour/texture triangles, alternating
  in-flight frames, both colour buffers and four malformed-geometry cases.
  Saved pre-change FPGA images were also checked for the original-profile cases.
- Thirteen HUD states matched the original glyph rendering exactly in CPU,
  serialized FPGA and queued FPGA rendering.
- Live Arduino calibration, firing, identified GPU frames and pausing after
  input loss passed after deployment; the test recorded a kill and 261 advancing
  ticks. A separate injected-PIPE test recovered the real USB connection with
  exactly one reset and received five fresh samples with no remaining error.
- The normal broker then stayed fresh in all 45 once-per-second observations
  over 44 seconds, with 220 new samples and no generation changes. This is a
  bounded health check, not a long-duration reliability claim.
- With complete-frame yielding enabled, all 450 observations at 100 ms intervals
  over 44.90 seconds were fresh, including publication age. The stream advanced
  224 samples, had no generation changes, and its maximum observed sample age
  was 231 ms. The selected yield was confirmed as 150 ms in every snapshot.
- The expanded 256-frame FPGA gate also passed with the yielding Arduino reader
  live: zero additional pixel differences, 97 sensor samples received, no
  generation changes and fresh data at completion. The deployed full-game smoke
  passed calibration, firing, a kill and focus-loss pausing with 212 advancing
  ticks. Captured throughput was 10.43 FPS over that short test, versus 5.21 in
  the preceding non-yielding smoke; neither is displayed browser FPS.

**The strict original-reference fidelity requirement is still unfulfilled.**
Before these software optimizations, the FPGA's serialized W16 renderer already
differed from the commit's CPU image by 167–979 pixels across the seven sampled
320×240 frames, even after RGB565 quantization. No tolerance was increased and
this difference has not been concealed as a pass. Zero *additional* FPGA pixel
differences does not mean zero differences against the original CPU renderer.

## Performance

The identical bounded moving-game pipeline benchmark, without web/sensor load,
improved from 13.61 completed FPS to a best tested 16.55 FPS. This is not browser
FPS or a guaranteed maximum. Command submission/rendering still took about
49 ms median in that run, beyond the 37.04 ms frame budget for 27 FPS. Geometry,
preparation and readback overlap; their times must not be summed as if serial.

An intermediate restored-profile browser run measured 5.14 displayed FPS over
14.98 seconds of visible, active gameplay. It preceded the final command-cache,
inline-validation and coverage-rejection changes. The final browser result is
recorded separately after measurement. An intermediate build subsequently measured
**5.80 displayed FPS over 30.00 seconds**, with one visible browser and 1712
advancing simulation ticks. GPU frame-counter advancement was 11.10 FPS and
server collection 8.07 FPS. Median geometry/preparation/submission/readback
were 12.35/17.67/46.14/6.20 ms. Thus delivery loses further frames, and queue and
publication timing is being instrumented before assigning the remaining gap
to any hardware limit. The instrumented controlled run found median ready-queue
wait 11.44 ms, slot-ownership wait 0.009 ms, previous publication 1.53 ms and
scene-lock wait 0.002 ms. Publication is on verified tmpfs, not the SD card.
After the final geometry changes, the controlled run's median ready-queue wait
was 4.06 ms, slot wait 0.009 ms, previous publication 1.56 ms and scene-lock wait
0.002 ms. Geometry used about 25.42 ms of thread CPU time, preparation 21.74 ms
and the GPU-owner path 47.63 ms in that workload. These CPU costs, plus readback and web
handling, remain too high; a hard RTL FPS ceiling has not been established.

The USB investigation exposed another source of contention: with the same
paused scene and browser, the game ran around 13 FPS when the USB endpoint was
stalled, and around 5–8 FPS with live samples. Continuous 512-byte reads generated
roughly 65,000–73,000 USB interrupts per second in a six-second A/B/A trial.
64-byte reads and short yields did not demonstrate a repeatable frame-rate
improvement. A short-timeout polling trial lost over half the sensor samples;
the fastest yield trial had no live samples at all. Neither counts as a fix.
This implicates active USB traffic/host-driver contention, but does not isolate
the exact kernel or bus mechanism. The original bulk-transfer arguments are
retained; the complete-frame idle interval described below is now selected.

### Separating setup arithmetic from GPU writes

A separate library redirected only Glide triangle-register stores to a volatile
RAM sink. The same seven prepared scene captures were submitted 18 times each,
discarding three warm-up frames. The real/RAM/real sequence used the production
library for both real passes; its hash and source were unchanged afterward.
For tick 180, median command time was 51.30/9.12/51.30 ms. Across the seven scenes,
real submission was 33.04–51.30 ms; RAM-only setup was 4.38–9.48 ms. Real images
had one stable hash per scene, identical before and after the diagnostic.

The RAM-only run deliberately does not render the game and provides no valid
game FPS. It shows that removing CPU setup arithmetic alone cannot recover most
of the submission time; GPU register traffic, processing and backpressure are
material. The busy counter also includes FIFO occupancy and synchronization
waiting, so its 31.28–45.00 ms range must not be presented as pure raster time or
a proven maximum FPS. No specific RTL defect is established by this experiment.

Evidence: `setup-cost-summary.json`, `setup-v2-*-setup-cost.json`,
`probe_setup_cost.py` and `run_setup_probe.py`. The first probe's Python ctypes
double-return clock readings were constant zero and are invalid. Version 2
records the valid C-to-C clock measurement from the native metadata instead.

### Complete-frame USB yield candidate

Yielding only after a complete valid sample avoids interrupt-heavy outstanding
bulk reads during most of the measured 5 Hz stream's idle interval. Original
512-byte transfers and 200 ms timeouts are retained, and samples are published
before waiting. A 150 ms quiet interval in the initial six-second test reduced
USB interrupts from 67,032/s to 16,305/s and increased paused-game completed FPS
from 7.33 to 12.49; the return baseline was 6.33 FPS. Every interval retained
about five samples per second with no reconnects.

A 12-second A/B/A repeat of the reader implementation measured 6.50/13.06/7.00
completed FPS and 70,309/17,435/70,004 USB interrupts/s. Every interval received
60 samples with identical sequence coverage and no reconnects or stale endpoint.
Relative arrival-lag medians were -6.47/1.95/6.86 ms and p95 values
14.87/33.48/26.27 ms, using one firmware/local-time anchor for all intervals.
These are controlled paused-game results, not displayed gameplay FPS.

The selected change skips its wait when a read contains a partial next message.
The guarded 12-second A/B/A repeat measured 5.49/12.91/7.74 completed FPS and
73,578/17,396/64,646 USB interrupts/s. Each interval again retained 60 samples,
identical sequence coverage and zero generation changes. Relative arrival-lag
medians were -17.31/-11.26/-3.51 ms, with p95 6.19/5.06/25.20 ms. This confirms
the gain in another fixed paused workload without a measured sample-rate loss.

The CLI and service now select 150 ms; `--frame-yield-ms 0` restores the original
reader timing. The library constructor retains zero as its default so isolated
baseline harnesses stay explicit. The setting is tuned to this board's measured
USB sample cadence, not inferred from the firmware's advertised 40 Hz counter.
Evidence: `usb-frame-yield.json`,
`usb-frame-yield-exact-before-partial-guard.json` and the guarded repeat
`usb-frame-yield-exact.json`, plus `sensor-yield-pixels.log`,
`sensor-yield-validation-health.json`, `sensor-yield-health.json` and
`sensor-yield-game-smoke.json`.

After the final deployment, `live-fps-20261108-013241.json` recorded 31 samples
over 30.75 seconds. The game started on its game-over screen and was restarted
near the end. Only 4.22 seconds met the visible, active, same-browser criteria:
13 acknowledged frames, **3.08 displayed FPS**, with 200 advancing ticks. The
active-snapshot median geometry/preparation/submission/readback times were
22.76/34.51/81.19/6.03 ms. This short, different game segment is not a sustained
30-second result or a controlled before/after comparison. A follow-up capture,
`live-fps-20261108-013343.json`, found the tab hidden and the game paused
throughout, so it has no valid active FPS result. The earlier 5.80 FPS run was
the last complete visible-gameplay measurement before the USB fix.

### Selected build: continuous active browser measurement

`live-fps-active-20261108-015751.json` records **15.484 displayed FPS over 30.031
continuous seconds**: 465 canvas-acknowledged frames, one visible browser,
1804 advancing simulation ticks (60.07 Hz), no pauses or game-over intervals,
and fresh Arduino data in every active sample. The capture waited for active
play instead of counting the preceding hidden/paused time. It changed no input
or browser state. The game ran at 320×240, scene 6, complexity 18, full range 1,
quality `low`; these arguments and the reader's 150 ms setting were verified
against the live processes afterward.

GPU frame-counter throughput was 17.55 FPS and server collection 17.12 FPS.
Median geometry/preparation/submission/readback was 18.78/20.00/41.19/6.95 ms;
submission p95 was 75.42 ms. Median native publication-busy time was 34.66 ms,
which includes FIFO/sync waiting. Median browser send-to-ACK time was 12.30 ms.
The visible path covered ticks 281–2085, HP 92–70, with a median 1367 submitted
triangles. This trace differs from the earlier 5.80 FPS session, so their ratio
is not a controlled same-scene speedup; the paused A/B/A tests establish the
USB change's causal improvement separately.

The end-to-end 15 FPS level is now measured with the live Arduino broker. The
27 FPS minimum is still unmet. Driver/GPU submission and its latency spikes
remain the main measured limit; browser delivery alone cannot close the gap
between 15.48 and 27 FPS when only 17.55 completed frames/s are available in
this run. The measurement source is `measure_visible_game.py`.

### Cached scenery projection prefixes

The next selected change caches the first two terms of the camera dot products
for immutable chunk vertices. It does not distribute/reassociate the remaining
Z arithmetic, change vertices/indices, or reduce scenery. On ARM, all seven
geometry and CPU-image hashes matched both the pre-cache implementation and
the original commit's ARM reference. A live comparison of original-transform
frames with queued cached-transform frames passed **84 FPGA frames with zero
additional differing pixels**, including both colour buffers and HUD textures.

The isolated 300-frame ARM geometry A/B/A sample measured median
11.571/10.832/11.258 ms, with about 0.4–0.5 MB additional retained memory in the
enabled sample. The cache is bounded by the immutable chunk arrays. The whole
moving-game A/B/A pipeline measured 15.62/16.69/15.93 completed FPS without web
or sensor load. This is a modest gain and does not establish a 27 FPS result.

The cache-enabled build is deployed. Its real sensor/game smoke passed
calibration, a kill, input-loss pausing and 209 advancing ticks; captured
throughput was 10.80 FPS over that short test. The complete 15.48 displayed-FPS
measurement above preceded this cache change; a new 30-second visible-browser
measurement has not yet been obtained for the cache-enabled build. Neither
the isolated throughput nor the short smoke is a replacement for that result.

Evidence: `xy-cache-results.json`, `xy-cache-validation.json`,
`xy-commit-arm-reference.log`, `xy-reference-before.log`,
`xy-reference-after.log`, `xy-cache-gpu-pixels.log`,
`xy-pipeline-*-pipeline.json` and `xy-cache-game-smoke.json`.

The 27 FPS minimum has **not** been demonstrated. The software-only work is not
complete against all requested gates; the original-reference mismatch also
remains. No FPGA RTL or bitstream has been changed to address either issue.

The next software performance work should target the native Glide triangle
setup/MMIO path and active USB host contention. Even without web/sensor load,
the selected command-submission median is 48.65 ms, above the 37.04 ms budget
for 27 FPS. Reducing browser delivery overhead alone therefore cannot make this
measured workload sustain the target. Any further driver candidate still needs
exact pixel comparisons before integration. This is a measured priority, not
proof that RTL is correct or that the GPU has a particular maximum frame rate.

### Setup-register cache: rejected for lack of throughput improvement

A broader cache compared exact float bits and physical register addresses for
triangle setup registers, while leaving triangle commands and synchronization
unchanged. Both disabled and enabled configurations passed 288 FPGA frame
comparisons with zero additional differing pixels. It reduced the median float
register writes from 47,721 to 38,643, but moving-game A/B/A throughput was
16.49/16.36/16.23 FPS. The production change was rejected; its two source files
remain isolated under `build/software-profile/setup-cache-prototype/`.
Evidence: `setup-cache-{before,enabled,after}-pipeline.json` and
`setup-cache-{off,on}-pixels.log`.

### Readback wakeup scheduling

A separate instrumented library located about 8 ms of post-render wall time
at the submission thread's mutex unlock, when the readback worker wakes up.
The lock acquisition itself took about 0.002 ms. This is a scheduling delay,
not 8 ms of mutex computation. The diagnostic used an executable/library copy
and verified that production sources and binaries were unchanged.

Giving only the readback worker `SCHED_BATCH` reduced the diagnostic tail from
about 8.13 ms to 0.12 ms. The short moving-game A/B/A test reached
16.34/16.96/16.21 completed FPS; time moved between pipeline stages, so removing
the tail did not save 8 ms from every complete frame. Linux documents this
policy as reducing wakeup preference for a CPU-intensive thread, with priority
zero: [Linux scheduling policies](https://man7.org/linux/man-pages/man7/sched.7.html).

The minimal production candidate passed **288 FPGA comparisons with the policy
disabled and another 288 enabled, with zero additional differing pixels**.
Its longer moving-game A/B/A sample, covering ticks 60–1140 without web/sensor
load, reached **18.17/18.56/17.88 completed FPS**. Copy-time p95 was
23.50/7.14/26.48 ms. Capture latency median was 53.91/56.13/54.02 ms and p95 was
67.79/70.66/74.68 ms; the modest throughput gain is not a universal latency
reduction. These longer samples must not be compared directly with the earlier
600-tick runs as if their workload windows were identical.

The selected service enables `SPINAL_READBACK_BATCH=1`. Startup waits for the
worker to report its actual policy, and frame metadata exposes
`readback_policy` and `readback_policy_error`. The deployed worker reports 3/0.
No vertices, pixels, GPU commands, buffer-ownership rules or fences changed.
The live sensor/game smoke passed calibration, firing/a kill, 200 advancing
ticks and focus-loss pausing. Its short captured throughput was 10.92 FPS,
which is not an active visible-browser measurement. The last valid 15.48 FPS
browser measurement still predates the XY cache and this scheduling change.

Evidence: `copy-policy-{before,batch,after}-pipeline.json`,
`readback-policy-{before,enabled,after}-pipeline.json`,
`readback-policy-{off,on}-pixels.log` and `readback-policy-game-smoke.json`.
The diagnostic generator requires the SHA256-pinned `tail-probe-input.c` from
the pre-policy bundle, so it remains reproducible after the production change.
The 27 FPS minimum and original CPU-reference pixel gate remain unmet.

The post-deployment browser watcher ran for 150.09 seconds with no metrics
errors, but observed no continuously active visible-play interval. The tab
remained hidden/paused, so it cannot provide a new displayed-FPS result.
Evidence: `build/full-pipeline/live-fps-active-20261108-030223.json`.
The service remains running for the requested human-controlled measurement.

### Selected build: completed visible-browser measurement

After the user returned to the game, bundle
`197ff29d01b9ed1dba691646c1c8443fc63c7b89935ea92cff33c45fcf4c766a`
completed a fresh **30.984-second** uninterrupted active-play capture:
**472 canvas acknowledgements, 15.234 displayed FPS**. One browser remained
visible, the game stayed unpaused with no game over, the Arduino was fresh in
every observation, and simulation advanced 1860 ticks at 60.031 Hz. The reader
policy was 3 with error 0 throughout. There were no metrics errors or capture
interruptions. Ticks covered 422–2282, HP 85–57, and median submitted triangles
were 1406.5, with p95 3449.

The FPGA completion counter averaged 17.816 FPS and server collection
16.847 FPS. Median geometry/preparation/command submission/readback was
11.017/19.813/41.611/6.637 ms. Submission p95 was 71.762 ms; readback p95 was
26.989 ms. GPU-owner CPU time was 32.573 ms median. Median complete-frame
capture latency was 51.187 ms, p95 82.842 ms, and browser send-to-ACK median
was 13.174 ms. These pipeline stages overlap and their medians are not a
sum of end-to-end latency.

This is the latest valid displayed-FPS measurement, superseding the pending
notes above. The earlier 15.48 FPS result used a different human-controlled
trace; the latest result does not prove an end-to-end gain from the XY cache or
readback scheduling change. The controlled A/B/A tests support only their
modest isolated gains. Browser delivery improvements alone cannot reach 27 FPS
when this run produces about 17.82 completed frames/s. Native triangle setup,
MMIO submission/synchronization and their contention remain the measured
priority. This does not establish a hardware maximum or prove an RTL defect.

Evidence: `build/full-pipeline/live-fps-active-20261108-030350.json`.
The 27 FPS minimum remains unmet, as does the original CPU-reference pixel
gate; zero additional errors in optimized-vs-legacy FPGA comparisons does not
resolve that existing mismatch. Resolution, scenery, animation and FPGA image
were unchanged during this capture.

### Native compiler settings

An isolated library used `-O3`, Cortex-A9/NEON targeting and explicit
`-ffp-contract=off`, with no fast-math. Moving-game A/B/A throughput over the
same 1200-tick window was **18.50/18.98/18.44 completed FPS** without web/sensor
load. Preparation CPU median was 23.57/20.14/24.70 ms. GPU-owner CPU median was
43.73/44.14/42.80 ms, so this does not demonstrate faster GPU command processing.
It is a modest overall improvement, far short of the 27 FPS minimum.

The initial candidate passed 288 comparisons. The strengthened harness then
saved every reference from the selected pre-change library, including all
14 RPL scenes and eight generated subpixel/coverage scenes. The candidate
passed another 288 comparisons against these 22 saved references. Missing
references now fail when `FLIGHTING_VALIDATION_REQUIRE_BASELINE=1`. Both
serialized and queued results are checked against pre-change pixels, avoiding
the weakness of comparing two paths compiled with the same new settings.

The compiler settings are selected in `combat/board/build_native.sh`. The
deployed library passed its own 288-frame check against all 22 pre-change
references, with zero differing pixels. The isolated and deployed libraries
have identical code, read-only data and initialized data sections; ELF dynamic
metadata/build identifiers differ. Their exact hashes are retained in
`compiler-cross-reference.json`, `compiler-deployed-validation.json` and
`compiler-elf-differences.json`. The live smoke passed calibration, a kill,
211 advancing ticks and focus-loss pausing. Its short 11.07 captured FPS is
not displayed FPS. The latest 15.23 displayed-FPS measurement predates the
compiler change; the selected compiler build still needs that measurement.

Evidence: `compiler-{before,o3,after}-pipeline.json`, `compiler-o3-pixels.log`,
`compiler-selected-reference.log`, `compiler-o3-cross-reference.log`,
`compiler-deployed-pixels.log` and `compiler-game-smoke.json`.

### Further geometry reduction trials

Extending the selected conservative union-grid empty-triangle search from
2x2 to 8x8 pixels failed its first 288-frame gate with 16 differing pixel
observations. Tick 2 repeatedly changed pixel (224,114), expected `FF636952`,
actual `FF525942`. The candidate was rejected before any throughput test; the
production 2x2 rule is unchanged. The exact cause is not established by this
test, and no correctness claim is inferred from the ideal triangle geometry.
Evidence: `coverage-span8-pixels.log` and `test_coverage_span.py`.

A CPU-only feasibility estimate of strict interior tile occlusion found zero
skippable triangles in the seven saved scenes, for the tested 4x4 and 8x8
tiles and depth margins. It excludes clipped/textured triangles and does not
combine coverage from multiple occluders. This rejects that specific coarse
prototype, not all possible occlusion methods. It is not a GPU pixel test or
an FPS result. Evidence: `occlusion-potential.json`,
`occlusion-potential-relaxed.json` and `probe_occlusion_potential.py`.

### Pixel workload versus command count

An isolated instrumented library replayed the same seven prepared scenes in
original-area / quarter-linear-size / original-area order. Each scene ran
18 times with the first three frames discarded. The synthetic middle pass
scaled only prepared screen coordinates; it retained the 320x240 framebuffer,
textures, depth policy, synchronization and triangle list. This deliberately
changes test geometry and is **not** a game optimization or valid game FPS.
No production source or binary was replaced by this diagnostic.

The number of actual triangle-command register writes was identical in all
three passes for every scene. For tick 180, 4,086 commands took
**50.73/22.77/51.04 ms**; FPGA publication-busy time was
**44.52/11.04/44.99 ms**. For tick 1200, 1,403 commands took
32.83/9.17/32.95 ms, with busy time 31.11/5.70/31.28 ms. All seven original-area
scenes had one stable pixel hash, identical before and after the middle pass.
The production library and source hashes were unchanged on restoration.

This is evidence that pixel-workload-dependent raster/framebuffer processing
and resulting submission backpressure are substantial limits, beyond CPU
geometry construction or triangle command count alone. Shrinking geometry also
changes overdraw, depth/texture accesses and locality, so this experiment does
not isolate raster arithmetic from framebuffer bandwidth/latency. It does not
prove a hardware maximum, name an RTL defect or establish that software cannot
improve further. High GPU-owner CPU time alone must not be interpreted as time
spent only on setup arithmetic when submission duration changes this much with
pixel workload at a fixed command count.

Evidence: `pixel-cost-summary.json`, `pixel-cost-{before,small,after}-setup-cost.json`,
`probe_pixel_cost.py` and `probe_setup_cost.py`.

The tested software changes have not reached the 27 FPS minimum. The next
hardware investigation should count stall cycles at triangle setup, span
generation, framebuffer reads/writes and command FIFO acceptance, then replay
the unchanged original-profile scenes to locate the dominant wait. A hardware
optimization should follow those measurements and pass the existing pixel
gates before deployment. The CPU-reference mismatch remains a separate fidelity
issue to resolve; no RTL or FPGA image was changed in this software pass.

### Disabling unused HUD depth reads

The driver-state audit confirmed that opaque blending and dither subtraction
were already disabled. It found another avoidable memory path: depth-free HUD
draws selected `GR_CMP_ALWAYS` and disabled depth writes, while leaving depth
buffering enabled. `FramebufferAccess` issues an auxiliary-plane read whenever
`enableDepthBuffer` is set, independently of an always-pass comparison. The
generated RTL has this same read-enable condition. Thus these draws still
fetched depth values they did not use.

`pipe_draw_state` now selects `GR_DEPTHBUFFER_DISABLE` for a draw with
`Depth=false`, and restores W/Z depth mode for subsequent 3D draws. Comparison
and write-mask behavior remain selected per draw. This also lets Glide omit
unused depth interpolation where applicable. The original geometry, HUD font
atlas, simulation and animation are unchanged. The serialized reference path
remains available for validation and rollback.

The isolated candidate passed 288 queued frame comparisons against all 22
pre-change saved/generated references. Six additional synthetic scenes
interleaved depth-free solids, perspective-textured overlays, nearer/farther
3D draws and subsequent depth-free draws. Both baseline and candidate passed
72 queued comparisons each; this checks that depth mode is restored, that HUD
draws do not write depth, and that depth-free texturing retains perspective.
The deployed build independently passed the combined **360 queued comparisons
against 28 pre-change references, with zero differing pixels**.

In the seven static moving-game checkpoints, all raw pixel hashes matched
before/during/after the candidate. It saved about 5.0–5.6 ms per submission.
For tick 180, command time was 50.635/45.556/50.633 ms; for tick 1200 it was
32.869/27.310/32.865 ms. Triangle counts are unchanged; the fix removes depth
work for depth-free draws.

The full moving-game A/B/A sample reached **19.12/21.70/18.81 completed FPS**
over the 1200-tick benchmark without web/sensor load. Command-submission median
was 48.959/40.706/48.835 ms. Capture latency median was 58.66/49.42/58.31 ms,
and p95 was 71.38/62.86/71.62 ms. The 40.71 ms selected command median still
exceeds the 37.04 ms frame budget for 27 FPS; this is not a universal hardware
maximum. The earlier pixel-area diagnostic identified substantial
pixel-workload-dependent cost; this audit found software state causing part of
that work. The area diagnostic alone did not establish an RTL defect.

The live deployed game passed calibration, a kill, 205 advancing ticks and
focus-loss pausing, with fresh Arduino data. The short smoke captured 12.31 FPS
including transitions and pauses; it is not a visible-browser benchmark. A
new visible-play measurement is pending. The last complete displayed result,
15.23 FPS, predates both the compiler update and depth bypass.

The latest selected-build browser watcher waited 180.03 seconds without any
metrics errors, but the browser remained hidden and paused throughout. It
observed zero active-play seconds and therefore yields no new displayed FPS.
Evidence: `build/full-pipeline/live-fps-active-20261108-034021.json`.

Evidence: `depth-bypass-summary.json`, `depth-{before,bypass,after}-pipeline.json`,
`depth-{before,bypass,after}-setup-cost.json`, `depth-bypass-pixels.log`,
`depth-mode-validation.json`, `depth-mode-{before,bypass}.log`,
`depth-deployed-validation.json`, `depth-deployed-{pixels,modes}.log` and
`depth-game-smoke.json`. Source harnesses are `test_depth_bypass.py`,
`DepthModeValidation.cs`, `validate_depth_modes.py` and
`validate_depth_deployment.py`.

### Direct vertex storage: not selected

A CPU-only feasibility sample compared list storage plus a staging copy with
direct contiguous storage, using the original moving-game vertices. Over 300
measured frames, thread-CPU median was 8.82/5.06/9.01 ms in the A/B/A sample,
with seven byte-exact data checks. This excluded allocation/growth and was
not a game FPS result. The prototype was then compiled from isolated source
copies under `build/software-profile/vertex-candidate/`; production C# sources
were not changed.

The concrete vertex buffer avoids clearing unmanaged values when resetting
Count, and lends its pinned array synchronously to native preparation. The
prototype explicitly keeps the owner alive across that call. Pin-owner
finalization releases otherwise unreachable pinned arrays. Windows and ARM
checks passed for native-visible bytes, growth, shrink, reuse, repinning,
enumeration and pin-owner collection. The Windows game suite passed 428
checks. All seven ARM geometry and CPU-image reference checkpoints matched.
The candidate passed the combined 360 FPGA queued-frame comparisons against
28 pre-change scene references, with zero additional pixel differences.

The first CPU geometry comparison ran at low priority alongside the live game.
Wall medians varied widely (48.77/43.35/24.49 ms), and process CPU totals were
6.37/6.62/5.67 seconds. Those contended wall measurements do not establish a
geometry speedup. A controlled preparation sample with services stopped
measured median preparation at 14.111/10.864/13.365 ms. Mean packing was
3.163/0.296/2.959 ms; geometry medians were 10.864/10.357/10.361 ms. Managed
retained memory was about 0.8 MB lower in the prototype.

Full moving-game throughput improved only modestly:
**21.04/21.56/21.13 completed FPS**. With the real USB reader, web server and
one hidden browser, an identical paused scene containing 3,642 submitted
triangles measured **14.45/14.65/14.57 completed FPS** over roughly 20 seconds
per run. All observations stayed paused at tick 0 with fresh sensor data;
sensor cadence was 4.93/4.92/4.96 samples/s. Game CPU use was
148.08/142.29/149.62 percent of one core. These are paused-scene throughput
numbers, not active-play or displayed FPS.

The initial combined-load attempts failed during startup and produced no
valid benchmark. The harness was corrected to handle an HTTP endpoint that
had not bound yet and require consecutive healthy frame/sensor/browser
observations before measuring. Startup diagnostics are saved separately.
All runs restored the selected executable after stopping owned services.

The prototype's CPU savings did not produce a useful throughput gain under
the complete USB/web load. It was **not integrated**; its isolated sources
remain available for later CPU-bound work. The selected game remains the
depth-bypass build, executable SHA256
`c42205b3a28856372f6bc0f3540fbdc4862421353b24075a5808fc38b0b9a502`,
native library SHA256
`515618d24ac54cc0ca10aca2df7a1d75574b7f7c2653a740764d1360e1b75dbd`.
The game, sensor freshness and readback policy were verified after restoration.

Evidence: `direct-buffer-feasibility.log`, `vertex-cpu-results.json`,
`vertex-reference-arm.log`, `vertex-buffer-arm-checks.log`,
`vertex-prepare-{before,direct,after}.log`, `vertex-pipeline-summary.json`,
`vertex-direct-{pixels,depth-modes}.log`, `vertex-live-load-summary.json`,
`vertex-load-*.json` and `vertex-final-restored-health.json`. Source harnesses
and the experimental buffer are in `combat/experiments/software_profile/`.

### Latest selected build: 16.27 displayed FPS

Bundle `c87b88edf247491677f28b8d97a2ebab1414654e0708e41be34139214a3401f1`
completed a fresh human-controlled capture: **504 canvas acknowledgements over
30.984 uninterrupted active seconds, 16.266 displayed FPS**. One browser stayed
visible, the game remained unpaused without game over, and the Arduino stayed
fresh in every observation. Simulation advanced 1855 ticks at 59.870 Hz. The
readback policy remained 3/error 0. An earlier partial interval was discarded
when simulation paused; the reported window contains only continuous play.

The GPU completion counter averaged **17.719 FPS**, and server collection
17.493 FPS. The window covered ticks 1808–3663, HP 52–12, and a median 3,279
submitted triangles (p95 3,817). It is a different human-controlled workload
from the earlier 15.23 FPS capture, whose median was 1,406.5 triangles; their
ratio is not a controlled speedup measurement.

Median geometry/preparation/command submission/readback was
14.424/20.877/44.627/6.481 ms. Command p95 was 67.280 ms; readback p95 was
44.195 ms. GPU-owner CPU median was 36.986 ms. Complete-frame capture latency
median/p95 was 57.105/95.831 ms, and browser send-to-ACK median/p95 was
25.576/58.222 ms. These overlapping stages must not be added as end-to-end
latency. Native publication-busy median was 1,723,154 cycles at the verified
50 MHz clock; it includes synchronization/backpressure and is not pure raster
time or a proven maximum frame rate.

This closes the pending visible-play measurement for the selected software.
The **27 FPS minimum remains unmet**. Browser delivery alone cannot reach
27 FPS while the completion counter provides about 17.72 frames/s in this
workload. The remaining measured priority is triangle submission and the
pixel/framebuffer work it waits for. The independent command-count/area
diagnostic and rejected CPU-storage trial support investigating that path;
they do not prove that a particular RTL change will achieve the target.

No performance experiment ran concurrently with this capture. The selected
executable, native library, resolution, scenery, physics and FPGA image stayed
unchanged. The existing original CPU-vs-FPGA pixel mismatch remains unresolved;
zero additional errors against the pre-change FPGA references is a separate
validation result.

Evidence: `build/full-pipeline/live-fps-active-20261108-041741.json`.

## Evidence and reproduction

Raw logs and metrics are in `build/software-profile/`; browser measurements are
in `build/full-pipeline/live-fps-*.json`. Source harnesses are in
`combat/experiments/software_profile/` and `combat/tests/PipelineValidation.cs`.
Important logs include `reference.log`, `current-reference.log`,
`before-prepare.log`, `inline-validation.log`, `coverage-edge-pixels.log`,
`final-hud-equivalence.log`, `cpu-profile-summary.json` and the per-candidate
`*-pipeline.json` files. These build artifacts are intentionally not committed.
The selected controlled run is `selected-final-pipeline.json`; its pixel gate
is `selected-final-pixels.log`. USB experiments and recovery evidence are
`usb-continuous.json`, `usb-yield-live.json`, `usb-recovery-validation.json` and
`selected-recovery-game-smoke.json`. The final deployed runtime bundle SHA256
is `c87b88edf247491677f28b8d97a2ebab1414654e0708e41be34139214a3401f1`.

Production start command: `sh combat/board/start_service.sh`. The legacy loop is
available with `FLIGHTING_PIPELINE=0`; exact old binaries are in the rollback
archive. Individual prepared-packing, colour-cache and coverage candidates can
be disabled with `FLIGHTING_PACKED_REUSE=0`, `SPINAL_CACHE_COLORS=0`, and
`SPINAL_COVERAGE_REJECT=0`, respectively. Restore old scenery settings only for
historical benchmark reproduction, not as the current game's performance fix.
`HACKRPI_SENSOR_FRAME_YIELD_MS=0 sh combat/board/start_service.sh` restores the
non-yielding reader for a controlled comparison. The normal service uses 150 ms.
`FLIGHTING_CITY_XY_CACHE=0 sh combat/board/start_service.sh` disables the selected
projection cache. The pre-cache USB-optimized bundle is preserved locally as
`build/software-profile/before-xy-deploy.tar.gz`, with its executable and the
three pre-change source files alongside it. The selected native library is
`515618d24ac54cc0ca10aca2df7a1d75574b7f7c2653a740764d1360e1b75dbd`.
`SPINAL_READBACK_BATCH=0 sh combat/board/start_service.sh` disables the readback
policy for a controlled comparison. The previous complete runtime is preserved
as `build/software-profile/before-readback-policy-deploy.tar.gz` (SHA256
`431fff22ea7b90ec422faab561fd7bbb9f15d00c6c5f1336b2cd7cbf27cfdb9c`),
with the previous native library in `before-readback-policy.so` (SHA256
`e282ea7a45c984938d7bdeeb569a854c0bcb9ff87cd27be62e0f888949b42676`).
The pre-compiler bundle is `before-compiler-deploy.tar.gz` (SHA256
`197ff29d01b9ed1dba691646c1c8443fc63c7b89935ea92cff33c45fcf4c766a`),
with its native library in `before-compiler.so` (SHA256
`8709f01d6eb78e8b3c5767683d27fdeda175e340cc620084aa855e90ab91891e`).
The compiler reproduction harness pins that prior library and build script;
it does not silently compare the selected O3 build with itself.
The pre-depth-bypass runtime is `before-depth-bypass-deploy.tar.gz` (SHA256
`5f6a4adfcfa1b6fa9106b16b1d8e6eb896e990aefb026c1d7b0135cc5b3136e4`),
with its native library in `before-depth-bypass.so` (SHA256
`41747a1c14eaf12936d4dffa75775c2650deb974f6e08e448603b8a772f7b3b8`).
The experiment scripts explicitly require the pre-change source/library;
restore that rollback when reproducing the old-vs-new comparison. The six
additional depth-state pixel references are also saved locally under
`build/software-profile/depth-mode-reference/`.

Accepted SOF SHA256 remains
`e1366086d8d6badb5bd9c82f97d40293dcb44dee278c1f940cc8be8baf7c69b2`.
