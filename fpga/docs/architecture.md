# Memory and renderer integration

## Implemented v1

The Standard HPS DDR and Ethernet remain in the board's HPS configuration.
The custom peripheral is reached through the lightweight HPS-to-FPGA master.
The generated `soc_system.sopcinfo` assigns `framebuffer_pattern_0.control`
physical base **0xff240000**, span **0x40000**. The host maps only 0x27000
bytes for the default target: registers at 0..0x28, frame at 0x1000..0x267ff.
The full device aperture ends at 0xff27ffff. The default host mapping ends at
0xff266fff. These are CPU physical addresses, not `malloc` pointers.

One M10K framebuffer contains 38,400 packed 32-bit words (153,600 bytes), two
little-endian RGB565 pixels/word, top row first, 640-byte stride. It is written
by the pattern generator and read through the same 50MHz FPGA domain. There
are no DMA transactions and no HPS cache aliases of FPGA RAM. The host's
native accessor performs aligned 32-bit MMIO reads with barriers; its private
`bytes` snapshot resides in ordinary HPS DDR and is shared read-only with
display threads. There is one MMIO producer protected by an advisory process
lock. The kernel must supply uncached Device mapping attributes.

```text
IDLE --generate--> BUSY --last pixel--> READY --CPU copy + release--> IDLE
                  ignore commands      reject generation
```

RAM is not cleared on reset. It is inaccessible until a completed generation
publishes READY. Sequence increments only after the last write; hardware cannot
overwrite READY. Host reads metadata, copies every pixel, verifies READY and
sequence, and releases before publication to the server. Exceptions during
copy release the frame; a timeout during rendering leaves it running for a
later recovery attempt. Network stalls never retain hardware ownership.

This is a bring-up architecture. Serial generation/copy limits throughput;
the completed-frame lock prevents tearing but does not provide overlapping
render and copy. No depth/texture allocation is yet connected to this peripheral.

## Selected 3D integration (not implemented)

Use SpinalVoodoo's native ARM Glide API and CPU triangle setup, FPGA raster,
depth and texture pipeline, existing HPS MMIO bridge and Avalon DDR backend.
The Nano project is a wiring reference; retain the Standard part, pins, HPS
DDR settings, Ethernet/SD multiplexing and compatible boot handoff.
See [the source audit](spinal-native-review.md) for exact interfaces and fixes.

The native API currently maps the full HPS-to-FPGA aperture at 0xc0000000,
16 MiB, with environment-overridable settings. This is distinct from the pattern
peripheral's lightweight bridge at 0xff240000. Assign and verify actual spans
from the generated system. Its word-addressed CPU input must receive byte
address bits [23:2], as in the upstream top; do not connect the v1 peripheral's
byte-address convention unchanged. Connect all active 32-bit Avalon masters to
HPS DDR through the Standard's configured FPGA-to-HPS SDRAM interface.

Use a verified reserved graphics pool or kernel-owned allocation with a known
FPGA bus/CPU physical translation. Never infer an address from malloc or assume
the upstream high-DDR constants are free in the installed Linux image. Unify
all address definitions: current Scala uses framebuffer 0x3f400000 and texture
0x3f800000, while older tools default to0x3f000000. These are source defaults,
not an allocation made by this project. Changing the bootloader memory limit
requires inspecting the actual image first. A later cached DMA allocation must
use DMA-API synchronization at each ownership transition; a cache flush is not
itself a renderer completion fence. Begin with verified uncached CPU mapping.

Initial frame sequence:

1. One host producer issues native clear/triangle/depth/texture commands.
2. At frame end stop submission, explicitly flush color and auxiliary buffers,
   wait for all pixel work and writeback queues to drain, and establish memory
   visibility across the Avalon/HPS DDR path. Current grSstIdle/swap status is
   insufficient: partial buffered runs can remain and pipeline idle excludes
   writeback busy. A publication operation must have a tested completion fence.
3. Read RGB565 through grLfbReadRegion into private HPS RAM with the correct
   320x240 stride/origin. The native stack already has aligned LFB readback.
4. Publish the immutable CPU snapshot to the existing latest-only stream.
5. Only after capture releases ownership may the FPGA reuse that buffer.

This first implementation can serialize rendering and readback without browser
backpressure. For overlap, use FREE -> RENDERING -> READY -> COPYING -> FREE
bank states. Drop unclaimed stale READY frames; never overwrite COPYING. A
triple-color-bank arrangement is an option only if the core's buffer-selection
logic is extended/configured and tested accordingly; it is not current wiring.
Depth can be shared only between non-overlapping frame submissions. Textures
remain immutable while referenced by in-flight work; updates need a fence or
another allocation. A full command FIFO or swap request is not memory completion.

A relative allocation budget at 320x240 is 153600 bytes per RGB565 color bank,
153600 bytes for Z16, plus aligned texture pages and command/metadata storage.
Match the selected native core's actual layout/stride/buffering rather than
forcing the pattern peripheral's tightly packed layout onto it. Verify depth
clear, compare mode and quantization using reverse-order overlap tests.

Add explicit headless generation/build options: no HDMI scanout traffic, no
ADV7513 initialization and no X11 link requirement. Use grBufferSwap(0) or a
verified virtual retrace rather than waiting on a disconnected display clock.
The CPU supplies scene transforms/setup; actual coverage, depth and texture
work remains in FPGA logic. First verify clear/readback, then flat triangle,
depth overlap, rotating cube and textured cube. The server remains a pixel
display and reports hardware render/capture/browser rates separately.