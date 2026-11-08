# Restore the known-good DE10 game

This directory contains the actual accepted FPGA image and matching game runtime,
stored directly in Git. A normal clone downloads the binaries; Git LFS and the
old `D:/GPU_proj` directory are not needed. The release tag is
**`de10-known-good-16fps`**. It preserves the source checkpoint `a0d3a3d`,
320x240 rendering, the original scenery/gameplay/animation, and the configuration
measured at 16.27 displayed FPS over 30.98 seconds. Frame rate depends on the scene.

## Requirements

- The same DE10-Standard and its existing working Linux microSD image
  (ARMv7 Linux 4.5, glibc 2.20, Python 2.7, libusb, native GCC).
- On the computer: Git, Python 3.9+, OpenSSH/SCP, and a direct Ethernet connection.
- For C# compilation on Windows: the .NET Framework 4 compiler, normally supplied
  with Windows. The saved executable also works without recompiling.
- To restore FPGA configuration: Quartus Programmer with Cyclone V support and
  the DE-SoC USB-Blaster cable. Synthesis from RTL requires Quartus Lite
  25.1std.0 build 1129, JDK 17 and the pinned Scala CLI toolchain. Those development
  tools are installed separately; their installers are not part of this backup.

This is a backup of the computer project and its runnable FPGA/game artifacts.
It does not replace a backup of the board's Linux SD card or Arduino firmware.
The Arduino's current firmware is retained; recovery does not flash it.

## Fresh clone and run

Keep the old directory until this verification succeeds. From a new directory:

```powershell
git clone --branch de10-known-good-16fps https://github.com/kaitophuc/hackRPI.git hackRPI-restored
cd hackRPI-restored
python recovery/recover.py verify
python recovery/recover.py build-game
python recovery/recover.py install --start
```

`build-game` compiles and self-tests the checked-in C# source. `install` restores
the exact accepted executable and native library, private Mono runtime, MMIO
support, USB reader, web server, and launch scripts. It verifies the transfer,
stops an existing owned game before replacing files, runs the ARM self-tests,
audits DDR ownership, enables the reviewed DDR ports, and starts the service.
The native renderer is already built, so this path needs no driver compilation
or downloads from Mono/SpinalVoodoo servers.

Open **http://169.254.170.29:8081/** and press Play / Resume. For Arduino controls,
hold the normal grip and use Calibrate & Play. All saved assets are checked
against `known-good-16fps/manifest.json` before installation.

The board must already be running the accepted FPGA image. If FPGA configuration
was changed, restore it first using the sequence below. A Git checkout cannot
change an already programmed FPGA.

## Restore FPGA configuration

Boot the existing board Linux SD image first. With Ethernet working and both
the JTAG and UART USB connections available, run:

```powershell
python recovery/recover.py program --quartus-bin D:/Quartus/quartus/bin64
```

The Quartus path is an argument and may point to another installation. The
command stops the existing game/diagnostics, programs the saved SOF at JTAG
position 2 on `DE-SoC [USB-1]`, then uses the checked-in guarded HPS warm-reset
script. Its FPGA ID, board pins, DDR handoff and 50 MHz configuration are the
accepted baseline, not a newly synthesized experiment.

After the warm boot, the temporary Ethernet address may need restoring. At the
board's UART root shell, use:

```sh
ip link set dev eth0 down
ip link set dev eth0 address 02:de:10:00:03:01
ip link set dev eth0 up
ip addr add 169.254.170.29/16 dev eth0
```

The computer needs a compatible address, for example `169.254.170.28/16`.
Then run `python recovery/recover.py install --start` again. Startup checks the
current boot's DDR exclusion before accessing the GPU. Existing boot behavior
and DDR evidence are described in
[the hardware bring-up guide](../fpga/docs/spinal-standard-bringup.md).

## Rebuild the native renderer from the bundled source

Use a separate fresh clone for this check. The archive contains the pinned
SpinalVoodoo Scala source, tests, complete Glide source and upstream license.
The matching platform patches are checked in under `fpga/patches/spinal`.

```powershell
python recovery/recover.py install --rebuild-native --target /dev/shm/hackrpi-recovery-build
```

This prepares and verifies the native patch locally, transfers the prepared
source, compiles the MMIO helper, Glide, diagnostic helpers and game native
library on ARM, and leaves the result in the board's RAM filesystem. It does
not start another GPU producer. The RAM directory avoids filling the current
board's almost-full root disk. A reboot removes this scratch rebuild.

For RTL development, use another fresh clone:

```powershell
python recovery/recover.py prepare --kind hardware
```

This restores `fpga/build/spinal-hardware-src` from the bundled source and applies
the accepted hardware patch. Follow
[the generator](../fpga/hardware/spinal_standard/generate-rtl.ps1) and
[the build script](../fpga/hardware/spinal_standard/build.ps1) with the separately
installed pinned toolchain. The accepted generated Verilog and ROM files are
already tracked in `fpga/hardware/spinal_standard/rtl`; running the saved game
does not require synthesis.

## What is preserved

| Artifact | Purpose |
| --- | --- |
| `Spinal_Standard_GPU.sof` | Exact accepted FPGA bitstream, SHA starts `e1366086` |
| `selected-runtime.tar.gz` | Exact selected game payload, executable and native renderer |
| `mono-armhf.tar.gz` | Private Mono 5.18.1 ARMhf runtime, including package licenses |
| `mono-packages.lock.json` | Original package URLs and SHA256 values |
| `mmio-support-armhf.tar.gz` | Prebuilt MMIO library and guarded DDR-port helper |
| `spinalvoodoo-source.tar.gz` | Pinned upstream GPU and Glide source, tests and license |
| `manifest.json` | Artifact hashes, accepted hardware-source hashes and measured baseline |

No SSH credentials, host trust file, browser sessions, sensor recordings or
machine-specific runtime logs are included. The existing CPU/FPGA image mismatch
and the unmet 27 FPS target are preserved limitations of this baseline.
