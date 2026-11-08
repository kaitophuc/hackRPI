# HPS boot and frame capture

Native capture was built and run on the connected HPS with GCC 4.9.3. The
`--check-pattern` command succeeded for sequence 1 at 320x240, producing
153600 bytes with SHA256
`26f49af01e3186f86a8d19ca5fc7cae11906dd9bf46e4e16d435cccafeef4b29`,
exactly matching the RTL simulation dump. Hardware reported 38400 cycles at
50 MHz (0.768 ms for test-pattern generation); the measured native copy took
15.634980 ms and capture took 16.716720 ms. These are pattern-generator
measurements, not triangle-rendering performance. The Python 2 legacy adapter
also captured successfully, with approximately 39.46 ms including process and
adapter overhead. See the final hardware report for retained evidence.

The preserved SD image runs Angstrom Linux 4.5.0 and identifies its device-tree
model as **Terasic DE1_SoC**. That model string is not a verified DE10-Standard
hardware description. The programmed Standard project and the operations
tested here worked with this existing boot image; its DDR/peripheral handoff
has not been certified as a complete Standard BSP. Do not generalize this
successful block-RAM/LW-bridge test to future FPGA DDR DMA compatibility.

For this tested direct Ethernet connection, the board is `169.254.170.29` and
the laptop is `169.254.170.28`. No Windows address change was needed. The
browser page is `http://169.254.170.29:8081/` while the server runs. These
link-local addresses apply to the observed session, not every future LAN;
record `ip -4 addr show` after reboot and use that board address.

For an existing image with Python 2 and native GCC, use the native capture path
without replacing the Linux image:

```sh
cd software
sh build_capture.sh
./capture --base 0xff240000 --check-pattern --output frame.rgb565
wc -c frame.rgb565
```

Run as root or with the appropriate physical-memory permissions. Build inputs
are `capture.c` and `mmio_access.c`; the script uses C99 and links `librt` for
older glibc clock support. Successful capture writes a 153600-byte default
RGB565 file and one JSON metrics line to stderr. `--stdout` emits only binary
pixels on stdout, allowing the legacy server to launch the helper and parse
metadata separately. Identity/geometry checks and bounded ready polling match
the modern API. The helper releases the ready framebuffer, reads back status,
unmaps MMIO and closes the advisory lock before writing output, so a blocked
pipe cannot hold the FPGA buffer. Failures return nonzero and never invent a
replacement image. The same kernel mapping and bridge prerequisites below
apply; programming and boot compatibility must be established first.

Existing microSD Linux is preserved. The v1 framebuffer lives in FPGA block RAM;
there is no DMA and no HPS DDR reservation. The CPU copies completed RGB565 pixels
through the FPGA bridge, releases the buffer, and hands immutable normal-RAM bytes
to the LAN server. This serializes FPGA generation and MMIO copying, but browser
consumption cannot hold the FPGA buffer. No cache flush is required on the copied
ordinary-RAM snapshot. **The MMIO mapping must be Device/uncached**, not a cached
alias. `/dev/mem` with `O_SYNC` relies on the running ARM kernel's physical-memory
mapping implementation; confirm it for the installed kernel before use. A UIO or
dedicated driver is the production replacement. The required `mmio_access.c`
helper issues volatile aligned 32-bit loads/stores, with ARM `dmb sy` barriers
before and after each access and compiler memory clobbers. Python `ctypes` only
calls this helper; it does not dereference MMIO itself. `ctypes` alone does not
provide volatile or I/O ordering guarantees. The helper checks address alignment,
range and pointer overflow. It cannot repair an incorrect kernel memory type,
recover a stalled bridge transaction, or prove peripheral write completion across
all interconnects. The status/sequence reads provide same-device readbacks in the
ownership handshake; actual HPS behavior must still be tested.

These choices follow the distinction between ordered I/O accessors and ordinary
memory accesses in [Linux's device-I/O documentation](https://docs.kernel.org/driver-api/device-io.html).
For production, put register access in a driver using `readl`/`writel` and an
explicit resource mapping. [Python's ctypes documentation](https://docs.python.org/3/library/ctypes.html)
defines native data access but promises no hardware I/O barriers. Review the
running kernel's ARM `phys_mem_access_prot` implementation, not only current
upstream source, when confirming `/dev/mem` mapping attributes.

First obtain the board serial console or SSH login and record this evidence:

```sh
uname -a
cat /proc/version
cat /proc/cmdline
tr '\000' '\n' </proc/device-tree/compatible
ip -4 addr show
ip route
cat /proc/iomem
ls -l /dev/mem
ls /sys/class/fpga_manager /sys/class/fpga_bridge 2>/dev/null
for b in /sys/class/fpga_bridge/*; do
    printf '%s: ' "$b"
    cat "$b/state" 2>/dev/null
done
dmesg | tail -n 100
python3 --version
```

Expected: an ARM Cyclone V SoC kernel and a DE10-Standard-compatible device tree,
and an assigned LAN IP. The modern server needs Python 3.7 or newer; native
capture and the legacy server support older Python 2 images. A detected JTAG
cable does not verify any of these. Board IP and current Linux image must be recorded in a hardware test
report. Do not substitute a DE10-Nano preloader, device tree, pin assignment, or
Platform Designer HPS handoff. The preloader and HPS DDR/I/O configuration must
match the Standard board and generated HPS configuration. An old working Linux
image can remain usable if the FPGA bridge clocks/reset and address map match;
that compatibility needs testing rather than assumption.

Before accessing physical memory, program the verified Standard bitstream, check
its generated `.sopcinfo` address map, and enable the appropriate HPS FPGA bridge
using the boot image's supported bridge mechanism. Do not write guessed clock,
reset, remap, or system-manager register values. Accessing a disabled/unclocked
bridge may hang the CPU; Python timeouts cannot recover a blocked bus transaction.
The generated `hardware/de10_standard/soc_system.sopcinfo` currently records
`framebuffer_pattern_0.control` at CPU physical address **`0xff240000`**, span
`0x40000`, in both `hps_0_arm_a9_0.altera_axi_master` and
`hps_0_arm_a9_1.altera_axi_master` memory maps. This is LW bridge base `0xff200000`
plus peripheral offset `0x40000`. The commands below use that generated map;
verify it again whenever hardware is regenerated. Host mapping span `0x27000`
covers registers and the default frame within the peripheral's larger aperture.
No device-tree overlay is needed for the temporary `/dev/mem` API, but a UIO driver
will require a resource node with the correct physical base/span and no competing
kernel driver. The host's advisory lock prevents two cooperating processes from
owning the peripheral; it cannot exclude unrelated raw-memory access.

Copy the `software` directory to the HPS over SSH, then:

```sh
cd software
sh build_mmio.sh
sudo python3 host.py --base 0xff240000 --span 0x27000 --check-pattern --output frame.rgb565
wc -c frame.rgb565
cat frame.rgb565.json
```

The build requires the HPS native C compiler (`cc`, normally GCC). Set `CC` to a
compatible compiler if needed. It builds `libgpu_mmio.so` and runs normal-memory
accessor/bounds tests. Expected helper output begins `PASS: native accessor` and
explicitly says it is not hardware MMIO evidence. Inspect the native ARM binary
with `objdump -d libgpu_mmio.so`: each accessor must contain word `ldr`/`str`
operations and `dmb sy` barriers. Build failure stops bring-up; there is no unsafe
Python-only MMIO fallback. Cross-compiling on the laptop is possible with an ARM
Linux toolchain matching the board's userspace ABI, but none is assumed installed.

Expected capture output for the default geometry: 153600 bytes, `source: hardware`,
`pattern_checked: true`, width 320, height 240, a completed sequence, and measured
copy/capture times. Failure to read ID `0x47505531` / ABI 1 stops capture before
commands. Geometry and format are checked before buffer access. Every ready wait
has a deadline. Capturing an already-ready frame recovers a frame left by a prior
process; otherwise the API requests a new pattern. The API reads aligned 32-bit
words, verifies sequence/status stability while copying, and releases the frame
before returning. A capture timeout does not invent a frame or silently fall back.

`render_seconds = render_cycles / clock_hz` measures the hardware generator only;
`copy_seconds` measures MMIO reads and host snapshot allocation; `capture_seconds`
also includes polling. Its reciprocal is producer throughput, not render FPS or
browser-delivered FPS. All hardware timing values remain unmeasured until this
command runs on the board.

For explicitly offline software checks of an existing dump:

```sh
python3 host.py --snapshot frame.rgb565 --check-pattern --output replay.rgb565
```

This reports `source: offline-snapshot` and zero hardware render timing. It does
not generate a scene and cannot count as FPGA or HPS verification. The host API
currently exposes only the test-pattern command; triangle, depth, texture, and
cube commands require the selected 3D renderer integration.
