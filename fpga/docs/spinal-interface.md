# Spinal Standard integration contract v1 — implementation work in progress

The proven pattern image remains intact in hardware/de10_standard. The 3D port
uses a separate hardware/spinal_standard project and separate generated files.
No agent may reprogram or reset the board without coordinating with root, which
owns COM3, active services, physical network settings and integration tests.

## Ownership

* Hardware owner: hardware/spinal_standard, patches/spinal/hardware-headless-fence.patch,
  hardware generator/build scripts and project-local toolchain setup. Generate
  and synthesize separately; retain all pinned upstream and vendor notices.
* Native owner: software/spinal and patches/spinal/glide-headless.patch; build
  native Glide/headless diagnostics and producer. Do not edit renderer RTL.
* Display owner: software/server.py, legacy_host.py and optional JPEG path, with
  source-compatible support for the already running test-pattern service.
* Root: shared preparation scripts, interfaces, integration files, board access,
  final docs/reports and hardware verification. Verification artifacts are kept
  under verification/spinal; tests must exercise real selected-core blocks.

Pinned upstream checkout remains clean under third_party/SpinalVoodoo. Apply
tracked patches to a prepared build/spinal-src tree; never silently change the
pinned checkout. Hardware and native patches must touch disjoint files. Coordinate
before editing the shared prepared tree; generation output is project-local.

## Address and clock plan (must verify generated map before use)

* Standard exact device5CSXFC6D6F31C6, existing Standard HPS DDR/pin handoff.
* Initially one50MHz FPGA clock and reset synchronized from HPS h2f reset.
* Existing native SST MMIO full HPS bridge base0xc0000000,16MiB aperture.
  The CoreDe10 CPU-facing address is a32-bit WORD index, unlike pattern v1.
* A new LW sidecar at0xff240000, span0x1000, replaces the pattern peripheral
  only in the new3D image. ID0x47505532 (GPU2), ABI2. Never let old capture.c
  silently accept this image. Wire framing remains GPU1/RGB565 for the browser.
* GPU DDR pool follows the unified pinned address definitions initially:
  framebuffer0x3f400000, textures0x3f800000; no DMA may be enabled until root
  verifies actual Linux/firmware ownership/reservation. Current Linux System
  RAM ends0x2fffffff, but that alone does not establish upper-DDR ownership.

## Sidecar ABI for native/render owner agreement

All offsets byte-addressed32-bit words, little-endian. Hardware owner may propose
changes before implementation if a source constraint requires them; message root
and native owner and update this contract first.

| Offset | Access | Meaning |
|---|---|---|
|0x00|R|GPU2 ID0x47505532|
|0x04|R|ABI2|
|0x08|R|bit0 pipeline busy, bit1 fence/flush busy, bit2 frame ready, bit3 sticky error|
|0x0c|W|1 request frame flush/fence;2 release ready frame;4 begin frame timing|
|0x10|R|width320|
|0x14|R|height240|
|0x18|R|CPU snapshot stride640 (native LFB stride/origin handled by readback API)|
|0x1c|R|wire format1 RGB565|
|0x20|R|completed frame sequence, increment on verified fence completion|
|0x24|R|last begin-to-fence cycles, includes CPU submission gaps; document honestly|
|0x28|R|clock50000000Hz|
|0x2c|R|last pipeline-busy cycles for occupancy instrumentation|

Host single producer/flock issues begin, clear/draw commands, native grSstIdle,
then explicit sidecar fence. Hardware holds flush on both framebuffer planes,
waits for pipeline and every active writeback/queue to drain, and exposes ready
only after a tested visibility condition. No idle/swap-only completion claim.
Native LFB readback copies all completed pixels to private HPS memory, verifies
sequence/ready stability, then releases before stdout/network can block.
No new draw commands are submitted during copying. LFB/control accesses needed
for readback remain allowed; do not gate all MMIO while ready and deadlock it.

Headless defaults: no HDMI scanout requests, no ADV7513 initialization, no X11
link dependency. Avoid retrace dependence: initial producer can read completed
backbuffer without swaps, or use tested grBufferSwap(0). One host producer owns
all graphics state. Serialized render/copy is acceptable for initial correctness.

## Native producer API and scenes

A native producer captures exactly320x240 little-endian RGB565, emits raw pixels
on stdout only, and emits one JSON metadata object on stderr. It releases GPU
ownership before output. Source hardware; sequence/render_cycles/clock_hz and
copy/capture times match the existing legacy adapter metadata schema. Add scene,
frame timing semantics and pipeline-busy counters without inventing performance.

Scenes in order: triangle, depth overlap (both submission orders), rotating
cube with explicit angle, textured cube with generated checkerboard. No game.
CPU transforms/setup through native Glide are allowed; actual coverage/depth/
texture operations must execute in the selected FPGA core. Provide deterministic
angles and depth expectations for pixel checks. Keep the pattern service working
until the3D build passes simulation, fitting/timing and memory-safety review.
