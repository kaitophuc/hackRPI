# Core investigation and selection

**Selected: SpinalVoodoo for the shortest credible Standard 3D port.**
RasterIX is the fallback. This decision follows inspection of the actual native
ARM software and memory interfaces, not similarity between FPGA board names.
The independent framebuffer diagnostic does not integrate either 3D core.

Repositories were inspected and pinned on 2026-11-07. No selected 3D core has
been generated, compiled or hardware-tested for the Standard in this workspace.
See [the detailed independent source review](spinal-native-review.md).

| Candidate | Revision | License | Source/build evidence | Decision |
|---|---|---|---|---|
| [SpinalVoodoo](https://github.com/fayalalebrun/SpinalVoodoo) | `92c56afa0e98763ccd794cd39512cad2822bd86e` | CERN-OHL-W-2.0 hardware; native Glide has separate licenses/notices | Scala 2.12.18, SpinalHDL 1.13.0, scala-cli, Verilator, Make/Nix. Actual ARM Glide MMIO backend, RGB565 LFB readback, native diagnostics, Avalon memory ports. Board target is Nano `5CSEBA6U23I7` | Selected, with Standard/headless/fence repairs required |
| [RasterIX](https://github.com/ToNi3141/RasterIX) | `3e2ee5aa5214b829c2a824250c445ce799ac8dc0` | GPL-3.0-or-later; retain dependency notices | Verilog, C++17, CMake >=3.23. Supported examples: Verilator, Arty Z7-20, Nexys Video, TE0890; no Quartus/DE10 target | Credible fallback; more new command/host/memory transport work |
| [GlandaGPU](https://github.com/stiangglanda/GlandaGPU) | `eed04d0dee9124ddfe755f9bc937c5da0fbdde78` | No root LICENSE found; do not assume redistribution rights | VHDL, Avalon-MM, 2D primitives, 640x480 RGB444 VGA; VUnit/Questa. Standalone QSF names Standard device | Infrastructure reference, insufficient as 3D renderer |

GlandaGPU's separate [Standard SoC integration](https://github.com/stiangglanda/GlandaGPU_SoC)
is pinned at `a61d2acf80ff959fc7efac9efed6d9fc3d190823`. No GlandaGPU RTL is
incorporated here. The board shell instead comes from the already installed
local Standard GHRD; its Terasic notices and source hashes are preserved.

## Why SpinalVoodoo

The native `de10/glide` and `de10/glide-tests` targets build an ARM graphics API
and about thirty diagnostics without requiring a game or DOS/86Box runtime.
`emu/glide/swlibs/newpci/pcilib/fxde10.c` supplies the HPS MMIO backend;
`glfb.c` supplies `grLfbReadRegion`. The platform can wrap clear, triangle,
depth, texture and readback calls rather than inventing a new command ABI.
CPU triangle setup already exists. FPGA hardware does the raster/pixel work.

`CoreDe10.scala` supplies the CPU bus bridge and six 32-bit Avalon memory
masters. The existing buffered configuration uses shared framebuffer write,
color read, auxiliary/depth read and texture ports. Import their bridges into
the verified Standard HPS configuration, preserving Standard DDR timing,
peripheral multiplexing, exact device and board pins. Never program the Nano
bitstream or reuse its HPS handoff as if it were the Standard.

Required repairs before claiming safe completed frames:

* Add explicit framebuffer flush, drain and publication fencing. The current
  buffered build ties `flushFbCaches` false, while final partial write runs can
  remain active and pipeline idle excludes writeback busy. `grSstIdle` or a
  swap alone is not sufficient evidence of DDR completion. Test partial runs,
  not just full-screen clears. Direct writes are an alternative first config,
  with separate write ports connected and in-flight visibility still fenced.
* Unify framebuffer/texture DDR addresses. Current Scala uses `0x3f400000` and
  `0x3f800000`; older capture/presenter tools use `0x3f000000`. Reserve memory
  in the actual installed Linux boot configuration before allowing FPGA DMA.
* Add a headless native build: the X11 presenter defaults off at runtime but
  headers/libraries are still build dependencies. Existing no-op presenter
  functions provide a small explicit headless path. Disable ADV7513 init,
  disable HDMI scanout requests and use unsynchronized swaps or a tested
  virtual retrace. No external monitor is required by the desired platform.
* Pin a compatible JDK and scala-cli. Generated DE10 RTL is absent in the
  checkout; installed Java 25 alone is not a validated Scala generation setup.

These are bounded changes in existing interfaces. They save a new RasterIX
host connector, command FIFO path and AXI memory-width adapter. This is a
source-based engineering recommendation, not proof of Standard timing or fit.

## Build/dependency evidence and resources

SpinalVoodoo pins Scala/Spinal dependencies in `project.scala` and its Nix
environment in `devenv.lock`. Upstream commands include `make de10/rtl`,
`make de10/qsys`, `make de10/bitstream`, `make de10/glide` and
`make de10/glide-tests`. These are **Nano** recipes and references to port,
not ready Standard instructions. No checked-in Standard utilization/timing
report was established. Its Nano throughput table cannot establish Standard
resource requirements or this platform's performance.

RasterIX supplies FPGA triangle/depth/texture work plus a C++17 GL-oriented
stack. `IBusConnector.hpp` is a clean seven-method software seam. Its wrapper
uses command/response AXI streams and an AXI memory master, so Cyclone V still
needs new host/command/memory integration. The potential adapter
`rtl/Util/AxiToAvalonBridge.v` is fixed at 16-bit data and emits word addresses.
Its 128-entry read FIFO has an unused full flag, and 256-beat bursts overflow
its 8-bit Avalon count. Existing tests cover four-beat stalls. It needs proven
request limits or repairs, not direct connection to the default 32-bit wrapper.

RasterIX's checked-in whole-design Xilinx results are Arty 15,446 LUTs,
15,899 registers, 17.5 BRAM tiles, 19 DSPs; TE0890 has 10,708 LUTs, 10,940
registers, 12.5 BRAM tiles, 19 DSPs. These are upstream reports, not Cyclone V
ALM/DSP fit estimates. It depends on bundled AXI/AXIS utilities, Float submodule
`83485654e380392a726ee67f8e5d2f4f8f73dd32`, bundled span and optional spdlog 1.10.
Its upstream tests use `cmake --preset unittest_software` or
`unittest_verilator`, CMake build and CTest. Native FT60X and Zynq DMA Proxy
presets are not DE10 build recipes. Local Rasterizer/TestFunc unit simulations
passed; full Icarus elaboration hit empty-for-step syntax in `PixelUtil.vh`.
That is simulator compatibility evidence, not a proven Quartus impossibility.

GlandaGPU documents `python run.py` / `python run.py --gui`, with Python 3,
`vunit_hdl` and QuestaSim. Its pinned script overrides the simulator path with
the author's Linux path outside GitHub Actions, requiring adaptation. The
standalone QSF is not a full HPS build. Advertised 640x480x12-bit VRAM implies
3,686,400 logical bits before packing/other logic; that is arithmetic, not a
fit report. No current Standard resource/timing report was established.

## Acceptance and fallback

First finish the independent Standard pattern -> HPS -> LAN milestones. Then
reproduce Spinal RTL, simulate bus/DDR completion repairs, build the Standard
port, and test native clear, triangle, depth overlap, rotating cube and texture
readback in that order. Publish only completed immutable CPU copies to the
existing LAN server. Render and browser delivery counters remain separate.

If Scala generation, Standard fit/timing or bounded memory repairs prove
impractical, evaluate the RasterIX port next. A minimal custom edge-function
rasterizer is a last fallback: fixed-point coverage and Z16 are feasible in
principle, but clipping, interpolation, texture correctness and API work lose
the existing software stack. No measured blocker currently justifies taking
on a new renderer. No game, terrain, player or collision work is included.
