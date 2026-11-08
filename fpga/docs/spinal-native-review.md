# Independent native-stack review: choose SpinalVoodoo for the shortest 3D port

This historical source-selection review predates integration. The Standard
GPU2 port and native HPS producer now run hardware triangle/depth/solid-cube
diagnostics; [current evidence](../reports/spinal-3d-result.md) records accepted
textures and the remaining queued-state limitation. Statements below describe the
upstream source at review time.

Reviewed pinned SpinalVoodoo `92c56afa0e98763ccd794cd39512cad2822bd86e`
against RasterIX `3e2ee5aa5214b829c2a824250c445ce799ac8dc0` on 2026-11-07.
This is a source review, not a generated, simulated, compiled, or hardware-tested
Standard 3D implementation. The independent framebuffer bring-up project is
unaffected.

**Recommendation: use SpinalVoodoo for the first 3D integration on the Standard.**
Its existing ARM-native Glide stack and Avalon DDR backend remove more new
implementation than RasterIX's cleaner GL-oriented interface. RasterIX remains
a good alternative when API compatibility outweighs bring-up effort. Calling
RasterIX the shortest path solely because it has `IBusConnector` understates
the transport and memory bridge work and misses SpinalVoodoo's native API.

## Actual reusable software

Paths below are relative to `third_party/SpinalVoodoo/`.

* `Makefile`: `de10/glide` and `de10/glide-tests` build ARM-native hardware
  libraries and diagnostics, independent of DOSBox/86Box/game workflows.
* `emu/glide/glide2x/sst1/glide/src/Makefile.de10`: builds `libglide2x.a` and
  `libglide2x.so.2`, defines `DE10_BACKEND` and `GLIDE_USE_C_TRISETUP`. CPU
  triangle setup is already provided; it is not an x86 assembly requirement.
* `emu/glide/swlibs/newpci/pcilib/fxde10.c`: hardware backend maps `/dev/mem`,
  with `DE10_VOODOO_BASE`, `DE10_VOODOO_SPAN`, and `DE10_VOODOO_MEM` overrides.
  Default aperture is the full HPS-to-FPGA bridge at `0xc0000000`, 16 MiB.
* `emu/glide/glide2x/sst1/glide/tests/Makefile.de10`: builds `test00` through
  `test29`, `sst1perf`, and triangle/texture stress scenes. `test00.c` clears
  the framebuffer; other tests exercise the native triangle API.
  `tests/tlib.c` recognizes `320x240`; the tests need explicit bounded frame
  counts and that resolution rather than their default 640x480.
* `emu/glide/glide2x/sst1/glide/src/glfb.c`: `grLfbReadRegion` implements
  `DE10_BACKEND` reads through aligned volatile 32-bit LFB accesses and packs
  pairs of RGB565 pixels into caller-owned rows. There is already a host
  readback API; direct physical-DDR dumping is not required for first capture.

The platform can wrap `grDrawTriangle`, clear/depth state, texture download,
and frame readback in its own small API. CPU vertex transforms remain platform
software work, just as RasterIX uses a CPU vertex pipeline. No game is needed.

The native Glide sources carry the separate license in `emu/glide/LICENSE`
and `emu/glide/glide2x/glide_license.txt`; the root hardware license alone
does not describe every imported component. Preserve all notices.

## X11 and HDMI can be removed, but are not absent today

`glide/src/gx11present.c` defaults the X11 presenter **off** for `DE10_BACKEND`,
so a running X server is not a runtime requirement for rendering. However,
Linux builds still include X11 headers and compile/link the presenter, and
`Makefile.de10` defaults `X11_LIBS=-lX11 -lXext`. Merely setting
`GLIDE_X11_ENABLE=0` does not remove that build dependency.

The file already ends with no-op `_grX11PresenterInit`,
`_grX11PresenterSwap`, and `_grX11PresenterShutdown` implementations.
Add an explicit headless build define guarding the X11 includes and full
presenter implementation, use those no-ops, and omit X11 libraries in that
configuration. Do not globally undefine `__linux__` to evade dependencies.
`init/initvg/de10_adv7513.c` supports `DE10_ADV7513_INIT=0`; headless
initialization must explicitly select that behavior or remove its call.

FPGA scanout is also currently real coupling:

* `src/voodoo/Core.scala` always instantiates `HdmiCdcFramebufferScanout`,
  enables it, and sets display dimensions to 640x480.
* `src/voodoo/de10/CoreDe10.scala` supplies the swap handler's vertical
  retrace from that scanout's `newFrame` status.
* `src/voodoo/frontend/SwapBuffer.scala` completes a swap immediately when
  vsync is disabled; synchronized swaps wait for retrace pulses.

For a headless first port, add a generation option disabling scanout requests
and use unsynchronized swaps (`grBufferSwap(0)`) or a documented virtual retrace
source. Avoid relying on an undriven HDMI clock or physical transmitter. Reuse
the core, not the Nano's HDMI board top or pin constraints. Readback must use
the requested 320x240 geometry and correct LFB stride/origin.

## Existing bus integration saves substantial work

`src/voodoo/de10/CoreDe10.scala` contains `H2fLwToBmbBridge`. Despite its
name, the checked-in board path uses the **full** HPS-to-FPGA aperture. Its
CPU-facing address is a 32-bit-word index; `De10PlatformTop.v` deliberately
passes `h2f_address[23:2]`, and the bridge shifts it left by two to recover
byte offsets. Do not accidentally connect byte addresses directly.

`CoreDe10` and `De10Top` expose six 32-bit Avalon memory masters:
shared framebuffer write, separate color write, separate auxiliary/depth write,
color read, auxiliary/depth read, and texture access. The selected buffered
board configuration uses the shared write port and the two read ports plus
texture port; separate write ports are inactive. With unbuffered writes,
the separate write ports must be connected instead.

`src/voodoo/de10/De10MemBackend.scala` provides BMB-to-Avalon translation,
read-response storage/backpressure and physical DDR address translation.
`hw/de10/qsys/create_de10_soc.tcl` exports four corresponding bridges to
`hps_0.f2h_sdram0_data`; it is a concrete wiring reference. Port these into
the verified **Standard** GHRD HPS configuration. Do not reuse that script's
Nano DDR timings, part, pinout, peripheral setup or handoff.

RasterIX, by comparison, needs a new HPS `IBusConnector`, command/response
transport, external framebuffer ownership path, and memory bridge integration.
Its `rtl/Util/AxiToAvalonBridge.v` is fixed at 16 bits and converts byte to
16-bit-word addresses. Its 128-entry read FIFO does not use `r_fifo_full`
to constrain accepted requests, and a 256-beat AXI request truncates the
8-bit Avalon burst count to zero. Existing bridge tests use four-beat stalled
reads, not maximum bursts. Reuse requires proving bounded request sizes or
fixing the adapter; it is not a ready general 32-bit HPS-DDR adapter.

## Critical SpinalVoodoo repairs before a completed frame can be published

The current native stack does **not** establish safe DDR-frame ownership.

1. `De10TopGen.scala` selects `useFbWriteBuffer=true` and 256-word buffered
   runs. `CoreDe10.scala` ties `core.io.flushFbCaches=False`.
   `framebuffer/FramebufferPlaneBuffer.scala` drains a partial active run
   upon explicit flush or a later rotation/full event. The final partial run
   can therefore remain buffered after drawing stops. Its `busy` expression
   only includes that active run while `flush` is asserted.
2. `core/PixelPipeline.scala` deliberately excludes framebuffer writeback
   busy from the status/synchronization pipeline-busy signal. It includes it
   for LFB-read safety, but that does not itself flush a partial active run.
   Native `grSstIdle` (`glide/src/gsst.c`, through `initIdle`) and swap
   completion are **not** sufficient DDR-completion fences.
3. `De10MemBackend.scala` acknowledges writes after Avalon accepts them;
   a dedicated publication operation must also establish visibility to HPS
   readback, including the appropriate same-memory readback/ordering proof.
4. `De10AddressMap.scala` currently puts framebuffer DDR at **`0x3f400000`**
   (top 12 MiB of a 1 GiB HPS memory), textures at `0x3f800000`. Old
   tools/presenter/scripts still default to **`0x3f000000`**. Unify these
   constants and reserve the entire FPGA-owned range in the actual boot
   configuration before enabling DMA. Never infer that range is free because
   a tool defaults to it. `mem=1008M` described upstream leaves 16 MiB free,
   but the current user's Linux image and reservations are unknown.

The smallest repair is an explicit frame flush/drain/publication handshake:
stop submission at frame end, flush both color and auxiliary buffers, wait
until all writers/queued operations are drained, establish DDR visibility,
copy the frame to HPS-owned RAM, then release/reuse the render buffer. The
browser sees only immutable HPS snapshots. Rendering can run independently
of browser consumption; first implementation may serialize capture and render.
Alternatively start with direct writes, wire the separate color/auxiliary
ports, and still add a completion fence accounting for in-flight writes.

Test the final partial word/run explicitly; a full-screen clear followed by
continuous drawing can hide this defect. Add command/backpressure, flush,
depth overlap, readback and ownership tests before trusting a rotating cube.

These are bounded integration fixes in existing blocks. They do not require
inventing a new renderer command ABI, C++ connector, or AXI width adapter.
That is why SpinalVoodoo wins the shortest-path comparison despite these bugs.

## Generation and acceptance gates

The local PATH currently supplies Java 25.0.1 but no `scala-cli`, `scala`,
`sbt`, or `cs`. Generated `hw/de10/rtl` files are absent in the checkout.
`project.scala` pins Scala 2.12.18 and SpinalHDL 1.13.0; generation needs a
supported JDK/scala-cli and Maven dependencies. Pin scala-cli and a compatible
JDK in the project tooling rather than assuming the installed Java 25 runtime
has been validated with this older Scala version. The upstream
`scripts/gen-rtl-de10` also requires Bash and GNU `timeout`; invoke scala-cli
directly from PowerShell or provide a reproducible Linux build environment.

Acceptance order after the independent pattern milestone:

1. Reproduce generated RTL from pinned dependencies and simulate the native
   MMIO/DDR backend plus flush/publication repair.
2. Import the core and Avalon bridges into the Standard shell, build and
   inspect actual utilization/timing. Nano results do not prove Standard fit.
3. Build the native headless API and run bounded clear/triangle/depth tests
   with captured pixels compared against expectations at 320x240.
4. Add cube transforms and texture diagnostics using the same native API;
   stream only explicitly completed, copied frames through the existing LAN
   server.

If generation, synthesis fit, or the bounded memory-coherency repairs fail,
retain the verified pattern/LAN infrastructure and evaluate RasterIX next.
No successful Standard 3D operation is asserted by this recommendation.
