# Depth-read RTL profile and isolated candidate

The accepted design is checkpoint `a0d3a3d` with generated-core SHA256
`bb2d5d4e5aa997f451bdb373093f55594cc6f2344f71ba9cc90dd12f5f32954c`.
The complete runnable rollback is tag `de10-known-good-16fps`.
This experiment preserves 320x240, game code, animation, geometry, textures,
the 50 MHz clock, memory ownership, board pins and completion fences.

## Measured cause and candidate

The accepted Avalon adapter starts another depth read only after the previous
read returns. With a 16-cycle diagnostic memory latency, the 64x32 rectangle
workload takes 74,302 cycles for 4,096 surviving pixels. Depth-request
backpressure stalls the framebuffer stage for 69,268 cycles. Changing only
memory latency to one cycle gives identical pixels in the smaller control
case and substantially reduces its time. FIFO synchronization and raster/TMU
input stalls propagate from that downstream read wait.

`De10PipelinedWordReader.scala` overlaps up to eight ordered, uncached word
reads on the direct depth-reader port. Every accepted request reserves storage
until its BMB response is consumed. Contexts retain their order; publication
stays busy through pending commands, memory responses and consumer stalls.
The direct reader emits aligned single-word reads. Cached-reader configurations
and the color, texture and write bridges retain the existing adapter.

`depth-reader.patch` selects the candidate in the prepared GPU source. No depth
values are cached or reused. Existing per-triangle synchronization remains.
The new block handles a zero-latency response as well as delayed responses.

## Small-scene results

| Diagnostic case | Accepted cycles | Candidate cycles | Framebuffer differences |
| --- | ---: | ---: | ---: |
| Depth, 16x8 rectangle, latency 16 | 4,990 | 1,206 | 0 bytes |
| Depth, 64x32 rectangle, latency 16 | 74,302 | 12,438 | 0 bytes |
| Depth, latency 64 plus request stalls | 17,343 | 2,757 | 0 bytes |
| Textured, 16x8 rectangle, latency 16 | 5,146 | 1,736 | 0 bytes |
| Blended, latency 16 | 4,990 | 4,990 | 0 bytes |

All 14 cases compare all 4 MB of framebuffer memory, including untouched
locations, both color surfaces and depth. They include nearer/farther overlap,
textures, alternating buffers, masks, delayed reads and request stalls.
Blending retains a serialized color read, so its unchanged time is expected.
These are simulation cycle counts with a controlled memory model. They are
not board FPS, full-game FPS, or a promise of 27 FPS.

Stage activity and wait counters overlap. A stage's input stall can be caused
by downstream backpressure. They must not be added as independent time totals.
The harness records normalized-LF source hashes for reproducibility.

The protocol suite passed 12 tests, including ordered contexts, an initially
blocked consumer, request-dependent memory grants, immediate responses, and
publication busy through the final response. The separate publication/fence
bench passed 11 checks. See `evidence/` for the results and board baseline.

The golden-frame archive preserves all 28 previously accepted board references,
verified against the original manifests. It must be restored to `/dev/shm`
after an HPS reboot before running the candidate's board pixel gates.

## Reproduce

Use the pinned JDK 17, Scala CLI 1.9.1 and Icarus tools. Start with the accepted
patched source. A recovery worktree can prepare it entirely from saved Git
artifacts:

```powershell
git worktree add --detach build/rtl-profile/recovery de10-known-good-16fps
python build/rtl-profile/recovery/recovery/recover.py prepare --kind hardware
python fpga/experiments/rtl_profile/prepare_candidate.py --baseline build/rtl-profile/recovery/fpga/build/spinal-hardware-src --output build/rtl-profile/candidate-src
```

`prepare_candidate.py` checks the accepted backend hash, applies the patch in
an isolated repository, and verifies the candidate content hashes. It refuses
an existing destination. Generate `SpinalStandardCore.v` from that source using
the unchanged `fpga/hardware/spinal_standard/SpinalStandardGen.scala`, with
`SPINAL_STANDARD_RTL` pointing to an ignored candidate output directory.

From the candidate source directory, run the platform Scala tests with:

```text
scala-cli test project.scala src <repo>/fpga/verification/spinal --server=false --jvm system --test-only platformverification.*
```

From the repository root, run the full-core comparison:

```powershell
python fpga/experiments/rtl_profile/run_matrix.py --candidate-rtl build/rtl-profile/candidate-rtl/SpinalStandardCore.v --output build/rtl-profile/matrix
```

The matrix stops at the first changed framebuffer byte. Its raw images and
compiled simulators stay under ignored `build/`. Golden references and source
patches are tracked. Simulation uses the entire accepted core, not a replacement
rasterizer; only its external Avalon memories are modeled.

## Hardware and board validation

Quartus 25.1std.0 full compilation passed. The fitted candidate uses 32,918 ALMs,
51,509 registers, 286 RAM blocks and the unchanged 62 DSP blocks. All constrained
timing entries pass; the minimum reported slack is 0.077 ns. The worst 50 MHz
setup slack is 2.217 ns. All 342 compiled signal-pin assignments, including all
72 HPS DDR pins, match the accepted image. The inherited unconstrained-clock
and peripheral I/O counts are unchanged; this is not a claim that those legacy
paths are fully constrained.

An additional Verilator test of the actual generated Qsys 32-to-256-bit memory
interconnect passed 64 ordered read responses with eight DDR beats pending.
It uses the unmodified synthesis interconnect source and enabled assertions.
Icarus could not advance that vendor fabric past time zero; the core and
protocol tests above use Icarus successfully. Questa compiled the vendor test
but could not run without a simulator license.

Candidate SOF SHA256:
`1af55209f870b807422caf18b2966a65745adcf6e22eef640f6de7b3260ab767`.

The candidate is programmed on the board. All 360 queued-frame comparisons
against 28 saved references passed with zero additional pixel differences.
The controlled seven-scene board comparison also retained every pixel hash.
For example, tick 180 command submission fell from 44.881 to 25.140 ms and
publication-busy time from 39.280 to 18.090 ms. That counter includes fences
and backpressure; it is not a measurement of pure raster time.

The real-browser test acknowledged 757 canvas updates over 30.016 continuous
active seconds: **25.220 displayed FPS**. GPU completion was 27.219 FPS and
server collection was 26.819 FPS. One browser stayed visible, the Arduino
stayed fresh, and simulation advanced at 60.001 Hz. Earlier paused intervals
were discarded. No competing profile ran during the active window.

The earlier accepted image measured 16.266 displayed FPS, but its human-play
window had a median 3,279 triangles compared with 1,371 here. Their ratio is
not a controlled speedup. The same-scene native comparison above establishes
the RTL improvement independently.

**The 27 displayed-FPS minimum is still unmet.** CPU preparation and frame
delivery require further measured work. Resolution, scenery, animation, game
executable and native library are unchanged. The original CPU/FPGA image
mismatch remains a separate unresolved issue.

`images/Spinal_Standard_GPU.sof` preserves this tested candidate. The fixed
`de10-known-good-16fps` tag retains the complete accepted recovery bundle and
its previous FPGA image. The candidate uses that same game/runtime software;
it is an experimental image rather than a replacement for that recovery tag.
`candidate-manifest.json` records the image, generated RTL and runtime hashes.
`evidence/visible-fps.json` contains the complete browser capture, including
the selected active samples and excluded paused intervals.

## CPU storage recheck with the faster image

The isolated direct-vertex prototype was rechecked after the RTL change.
It again passed 360 board pixel comparisons. Controlled preparation packing
fell from 3.098/3.213 ms in the surrounding baseline runs to 0.291 ms.
Moving scripted completion throughput was 29.500/29.911/29.314 FPS for
baseline/prototype/baseline, without the web server or Arduino reader.

With the real web server, Arduino reader and one hidden browser, the identical
paused 3,642-triangle scene measured 20.030/20.612/20.093 completed FPS.
Sensor cadence remained about 4.9 samples/s. These are controlled diagnostic
results, not displayed or active-play FPS. The approximately 2.7% combined-load
gain does not justify integrating the storage change; selected software was
restored and its hashes verified. The prototype remains isolated.

Reproduce the isolated gate/sample using `profile_vertex_on_candidate.py` on
the board after building the existing vertex candidate and restoring the 28
golden frames. It restores normal services in `finally`. The existing
`test_vertex_live_load.py` supports `FLIGHTING_PROFILE_DIR` for a separate
combined-load output directory. Results are saved in
`evidence/vertex-{on,load-on}-pipelined-rtl.json`.

A subsequent three-second CPU sample of the selected software on the paused
3,642-triangle scene located 26.55% of all game-thread CPU-clock samples in
native `_trisetup`, 10.68% in preparation, and 10.60% in readback. These are
software CPU-clock samples, not exclusive stage timings or an FPS estimate.
`sample_selected_cpu.py` captures the selected process without restarting it;
the existing `analyze_cpu.py` resolves native addresses.

The broader setup-register cache was rebuilt separately against the selected
native source, retaining depth bypass, O3 flags and readback scheduling. A
seven-scene before/cache/after sample retained every pixel hash, but command
medians differed by less than 1% relative to the initial baseline (with drift
in the later baseline). It was not integrated and no full-game speedup is
claimed. `sample_setup_cache.py` reproduces the isolated build/sample and
restores services; the optional `FLIGHTING_PROFILE_DIR` keeps its results in
RAM. See `evidence/setup-cache-on-pipelined-rtl.json` and
`evidence/selected-cpu-on-pipelined-rtl.json`.

## Follow-up depth-pair sample: synthesis in progress

`FramebufferPlanePairReader.scala` combines consecutive opposite halfwords of
the same word only while the first word command is still unaccepted. It never
reuses an issued or completed read. The ordered response remains held until
both requested halfwords are delivered. Accepted-pixel accounting keeps busy
asserted through FIFO prefetch bubbles and consumer stalls.

Only the direct auxiliary reader selects it. The color reader and cached-reader
configurations retain their previous paths. The framebuffer in-flight counter
is widened to cover the combined metadata and fetched queues as more pixels
can now be outstanding; the external debug field keeps its original width.

Against the tested eight-read candidate, the 4,096-pixel depth sample improved
from 12,438 to 7,042 cycles. Actual depth-word commands fell from 4,096 to 2,112,
and request-backpressure cycles from 7,610 to 2,152. All 4 MB of captured memory
are identical. All 14 full-core cases pass, including blending and both buffers.
The 15-test protocol suite covers stalls, same-cycle memory responses, reverse
lanes, repeated same-lane requests, and later requests to an already-issued word.
This is simulation evidence, not a board FPS result.

Prepare a separate source tree with `prepare_pair_candidate.py --baseline
build/rtl-profile/candidate-src --output build/rtl-profile/pair-src`, then use
the same generator and matrix commands above with the pair directories.
`create_pair_patch.py --verify-dir build/rtl-profile/pair-patch-check` builds a
complete patch from the saved upstream archive and verifies every Scala source.
Regeneration from that fresh patched source produced identical logic and all
eleven byte-identical ROMs; only the generator's Git-hash comment differs.

`pair_hardware_gate.py prepare` preserves the tested image/reports, checks
ports and ROMs, and prepares only the two generated core copies for compilation.
After the Quartus build, `pair_hardware_gate.py verify` checks timing, all 342
compiled signal pins, DDR pins, inherited unconstrained counts, and unchanged
board/constraint/memory inputs. The pair candidate is not programmed yet.
The tested 25.22 FPS image remains the current board configuration.
