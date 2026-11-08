# Bring-up interface v1 (agreed integration contract)

This interface is for the independently testable framebuffer peripheral, not the
RasterIX command ABI. All Avalon addresses below are **byte offsets**, 32-bit
little-endian registers, one clock domain, active-low synchronous peripheral reset.
Avalon reads have one cycle latency (`readdatavalid`); host writes use full words.
The physical HPS base is supplied at runtime after checking generated Platform
Designer address maps. `0xff200000` is only the conventional LW bridge start,
not proof that this peripheral is mapped there or that bridges are enabled.

| Offset | Access | Meaning |
|---|---|---|
| 0x00 | R | ID = 0x47505531 (GPU1) |
| 0x04 | R | ABI version = 1 |
| 0x08 | R | status bit0 busy, bit1 completed frame ready |
| 0x0c | W | command: 1 generate test pattern, 2 release completed frame |
| 0x10 | R | width (default 320) |
| 0x14 | R | height (default 240) |
| 0x18 | R | byte stride = width * 2 |
| 0x1c | R | format = 1 (RGB565, little endian, top row first) |
| 0x20 | R | completed sequence, increment only upon completion |
| 0x24 | R | last render cycle count |
| 0x28 | R | clock Hz (default 50000000) |
| 0x1000.. | R | completed framebuffer, two RGB565 pixels per word |

One framebuffer resides in FPGA block RAM. Generation is accepted only while
neither busy nor ready. Hardware never modifies a ready frame. HPS waits for
ready, copies **all** pixels to private RAM, then releases it. The browser only
receives that immutable HPS copy. A single producer owns MMIO; browsers cannot
directly issue register accesses. Polls have deadlines and geometry is validated.
This deliberately serialized bring-up contract prevents tearing without assuming
DMA cache coherency or a reserved HPS DDR region. Device MMIO must be uncached;
normal cached DDR is used only after CPU copying. Render throughput is limited by
copy time; browser backpressure must never delay release or the producer.

Test pattern at (x,y): RGB565 = ((x & 31) << 11) | ((y & 63) << 5) |
((x ^ y) & 31). Default frame is 153600 bytes; mapping span rounded up to pages
is 0x27000. Padding of an odd final pixel is zero. Host supports even width only
initially. Configuration means synthesis parameters, not unchecked runtime writes.

Raw WebSocket wire frame: 24-byte little-endian header `<4sIIIII`: magic GPU1,
sequence, width, height, format=1, payload bytes, followed by RGB565 payload.
Only one latest HPS snapshot is retained. Connection status and host metrics are
separate JSON text messages. No browser-side scene rendering or WebGL.

The 3D integration must add renderer commands and ownership-aware framebuffer
publication. This v1 pattern peripheral alone does not satisfy 3D acceleration.
