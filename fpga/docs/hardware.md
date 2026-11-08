# DE10-Standard hardware bring-up

## Evidence and identity

Current compiled/programmed evidence and limits are recorded in
[`reports/hardware-result.md`](../reports/hardware-result.md). This verifies FPGA
configuration and static timing. In the later UART bring-up, the HPS booted
Angstrom Linux 4.5.0 and a root-shell `devmem 0xff240000 32` returned
`0x47505531` after reprogramming the diagnostic SOF. Actual frame retrieval,
browser delivery and 3D rendering require their own evidence.

Local tool: `D:\Quartus\quartus\bin64\quartus_sh.exe`, Quartus Prime
25.1std.0 Build 1129 Lite. Read-only `quartus_pgm -l` detected `DE-SoC [USB-1]`.
`jtagconfig` returned HPS `4BA00477 SOCVHPS` and FPGA `02D020DD` with the generic
5CSEBA6/5CSEMA6 family string. That ID does not distinguish the package.
The Standard board project uses `5CSXFC6D6F31C6`, as confirmed against the
[Terasic Standard documentation](https://www.terasic.com.tw/cgi-bin/page/archive.pl?CategoryNo=200&Language=English&No=1106&PartNo=4).
Do not use Nano `5CSEBA6U23I7` pins or Lite MAX10 projects.

Board shell and HPS parameters were copied from
`D:\hardwareaccel\quartus\DE10_Standard_AI` into `hardware/de10_standard`.
The original Terasic copyright and restricted board-use permission remain in
the copied Verilog. This is local source reuse, not a claim that this workspace
has passed the old project's hardware tests. Dense-layer IP was replaced by
the original `framebuffer_pattern` component. Existing HPS DDR, Ethernet, SD,
UART pin multiplexing and handoff parameters are retained.

## Build

From PowerShell in the repository:

```powershell
$q = 'D:\Quartus\quartus'
Set-Location hardware/de10_standard
& "$q\sopc_builder\bin\qsys-generate.exe" soc_system.qsys --synthesis=VERILOG '--search-path=D:/GPU_proj/hardware/framebuffer_pattern_hw.tcl,$'
& "$q\bin64\quartus_sh.exe" --flow compile DE10_Standard_GHRD
```

The source peripheral is `hardware/rtl/framebuffer_pattern.v`; component metadata
is `hardware/framebuffer_pattern_hw.tcl`. The component uses byte addressing,
18-bit aperture, one-cycle valid response and full-word commands. Default
320x240 even-width geometry uses 38,400 words of M10K RAM. The renderer stores
two pixels per 50 MHz cycle; the measured cycle counter, not this estimate,
must be used on hardware. The FPGA-ready lock prevents modification while HPS
copies pixels. No cacheable shared DDR is used by this diagnostic.

Generated `soc_system.sopcinfo` must confirm the peripheral at LW offset
`0x40000`, aperture `0x40000`; expected HPS physical address is `0xff240000`.
The generated clock is the existing 50 MHz board input `CLOCK_50`, PIN_AF14,
3.3-V LVTTL, and reset follows the original HPS/GHRD reset network.

The original SDC is retained as `.reference.sdc` for attribution. The active SDC
constrains the 50 MHz FPGA clock and JTAG; generated HPS constraints cover the
HPS interfaces. Inactive VGA/FPGA SDRAM PLL references were removed. Human
switch/button inputs are declared asynchronous false paths. Review unconstrained
path reports before claiming a fully constrained platform. Timing warnings are
not a passing timing result. Inspect `output_files/*.fit.rpt`, `*.sta.rpt`, and
`*.map.rpt`. The board shell's constant reset was replaced with HPS h2f reset,
so the peripheral receives a real reset synchronized by Qsys.

The reference GHRD leaves 72 dedicated HPS DDR locations implicit. Quartus
reports this as missing-location critical warnings. `hardware/verify-pins.ps1`
compares every HPS DDR package pin in the completed `.pin` file against the
local Standard GHRD's prior compiled pin map (source and SHA256 recorded in
`hps-ddr-reference-pins.json`). The build script requires this comparison.
This check verifies the preserved Standard mapping; it does not establish
electrical calibration or successful Linux boot.

## Programming and boot

**Boot the existing microSD Linux first, then program this SOF through JTAG.**
The SD boot environment can load its own stock FPGA image. A power cycle or
reboot can therefore replace a previously programmed diagnostic image. During
bring-up, the first MMIO probe hung against that earlier image; reloading the
known diagnostic SOF after Linux boot allowed the ID read to return
`0x47505531`. Bridge `enabled` state alone does not identify the loaded design.

Only after compilation succeeds, with the Standard connected:

```powershell
& 'D:\Quartus\quartus\bin64\quartus_pgm.exe' -l
& 'D:\Quartus\quartus\bin64\quartus_pgm.exe' -c 'DE-SoC [USB-1]' -m JTAG -o 'p;output_files/DE10_Standard_GHRD.sof@2'
```

Expected programmer result: `100% (Successful)` and zero errors. JTAG is
volatile and does not install a new SD boot image. Do not flash persistent
configuration or overwrite the microSD until current files are backed up and
the generated HPS handoff has been checked against the installed bootloader.
Existing Linux may boot with matching Standard GHRD HPS settings, but that is
not established merely by successful FPGA configuration. UART boot and MMIO
evidence are recorded separately in the bring-up reports.

On the board collect `uname -a`, `/proc/device-tree/model`, `ip -br addr`, and
`dmesg`. Check bridge driver availability and enable the LW bridge using the
installed kernel's supported FPGA manager/bridge process. Do not blindly write
reset-manager registers or access `/dev/mem` while the bridge is disabled;
an unmapped/disabled bridge may hang the bus. Use the host probe at the address
confirmed in the generated map; expected ID `0x47505531`, ABI 1, 320x240,
stride 640, RGB565 format 1. See host documentation for capture and LAN startup.

No triangle renderer, DDR graphics allocator, 3D core port or VGA output is
included in this first diagnostic bitstream. The selected 3D integration plan
is in `core-selection.md`; the pattern peripheral is not a GPU substitute.
