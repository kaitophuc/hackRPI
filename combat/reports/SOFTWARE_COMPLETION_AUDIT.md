# Historical software pass: requirements and remaining work

The subsequent depth-read RTL measured **25.22 displayed FPS** and was accepted
by the user at 25 FPS. The table below records the earlier software-only pass.
Current hardware/browser evidence and the complete restore package are in the
[25 FPS recovery guide](../../recovery/README.md). Original CPU/FPGA image
differences remain separate from the passed zero-additional-difference gates.

Selected runtime bundle:
`c87b88edf247491677f28b8d97a2ebab1414654e0708e41be34139214a3401f1`.
Full evidence and reproduction: [software audit](SOFTWARE_PROFILE.md).

| Requirement | Current evidence | Result |
| --- | --- | --- |
| Keep 320x240 and original scene settings | Verified service arguments: scene 6, complexity 18, range 1, quality low; GPU open rejects another resolution | Met |
| Preserve original design, scenery, physics and animation | Seven same-platform ARM geometry/CPU-image checkpoints match commit `6b55fee2fd837894c211b46652201583ec096488`; original HUD comparisons also pass | Passed sampled fidelity gates |
| Preserve a rollback and identify reduced benchmark settings | Source/binary archives and hashes retained; earlier complexity 4/range 0.55 benchmarks identified explicitly | Met |
| Profile CPU, allocation/GC, preparation, submission, readback and delivery | Stage timings, CPU samples, allocation runs, command-count/area diagnostic and browser ACK capture retained | Met |
| Test memory and software candidates before integration | Isolated CPU/GPU A/B/A tests; candidates with pixel changes or insufficient useful throughput rejected | Met |
| Introduce zero additional FPGA pixel errors | Selected deployed library passed 360 queued frames against 28 pre-change references, including clipping, textures, depth transitions and both buffers | Passed sampled regression gates |
| Match the original CPU renderer with zero pixel errors | Existing CPU-vs-FPGA comparison still differs by 167–979 pixels/frame in seven checkpoints, even after RGB565 quantization | Unresolved; not a new optimization regression |
| Integrate and test real Arduino/game behavior | Calibration, firing/a kill, advancing ticks and input-loss pausing passed; latest visible run had fresh input throughout | Met |
| Measure one visible browser during sustained play | 504 canvas ACKs over 30.984 continuous active seconds: **16.266 FPS**; simulation 59.870 Hz | Measured |
| Sustain at least 27 displayed FPS, targeting 30 | Latest displayed 16.266 FPS; completion counter 17.719 FPS | **Not met** |

The task is not complete against the requested performance and original-image
gates. The selected software is running and the FPGA image is unchanged.
`build/software-profile/software-completion-audit.json` records the checked
runtime hashes and capture. A verified copy of the selected source/executable
payload, native library and manifest is saved as
`build/software-profile/selected-runtime-c87.tar.gz` (SHA256
`0ca88afa63fbb2935b93dad10ff9699e2faef653be54bb2a49feedf1ca0ee5f0`).

The measured remaining limit is triangle submission and pixel/framebuffer
processing/backpressure. The submission median in the latest play window was
44.627 ms, p95 67.280 ms. The frame budget for 27 FPS is 37.037 ms. Improving
browser delivery alone cannot supply frames that rendering has not completed.

Proposed next stage, outside this software-first pass:

1. Add simulation/debug stall measurements for command acceptance, triangle/span
   flow and framebuffer read/write waits, using the accepted RTL as the baseline.
2. Replay the unchanged representative scenes, then optimize the measured
   dominant stall while preserving geometry, depth/texture semantics and ownership.
3. Validate pixel equivalence and rollback before an on-board comparison; repeat
   the full visible-browser test. Treat the existing CPU-reference mismatch as
   a separate unresolved fidelity requirement.

No RTL implementation or FPGA programming for this proposed stage has started.

A read-only build precheck confirmed that the copied core RTL, wrapper, fence,
sidecar, generator, constraints, project settings and hardware patch match the
accepted textured-image manifest. Both retained SOF copies match the accepted
`e1366086d8d6badb5bd9c82f97d40293dcb44dee278c1f940cc8be8baf7c69b2`.
Quartus 25.1std build 1129, Icarus and the pinned Temurin 17.0.16+8 are present.
WSL reports Ubuntu/WSL2; a new simulation has not been run.

The copied FPGA project has no local tool/dependency cache yet. The existing
parent workspace has those tools and a SpinalVoodoo checkout at the required
`92c56afa0e98763ccd794cd39512cad2822bd86e` revision. An approved RTL build should
use a fresh pinned source export and the accepted patch, with those existing
caches, rather than assume a prepared source tree is clean. Evidence:
`build/software-profile/rtl-readiness-precheck.json`. No setup, generation,
synthesis or programming commands were run for this precheck.
