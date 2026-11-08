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

## Hardware gates and remaining work

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

Board validation still requires zero additional
differences against the 28 references, controlled before/after timings, and
30–60 seconds of actual displayed FPS with the Arduino and one visible browser.
The original CPU/FPGA image mismatch is a separate unresolved issue.
