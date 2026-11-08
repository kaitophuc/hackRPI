# Standard GPU2 build and board runbook

This is the SpinalVoodoo path. `hardware/de10_standard` and `software/host.py`
belong to the separate GPU1 pattern fallback. Current measured results and the
accepted SOF hash are in [the verified 3D result](../reports/spinal-3d-result.md).

## Build on this Windows host

Use Windows PowerShell from `D:\GPU_proj`. Dependencies are pinned in
`dependencies.lock.json`; preparation exports an owned build copy and applies
the tracked patches without changing `third_party/SpinalVoodoo`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-deps.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File hardware/spinal_standard/setup-toolchain.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File verification/spinal/run-buffer-tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File verification/spinal/run-publication-tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File hardware/spinal_standard/build.ps1
```

`build.ps1` generates RTL, the Standard wrapper and Platform Designer system,
then runs full compile and the 72-pin comparison. Review its exit code plus
newly timestamped fit, timing and DDR reports, rather than old output files
left by a failed build. Review combinational loops and inherited unconstrained
peripheral paths explicitly. The active FPGA clock is 50 MHz.

Platform Designer's HPS sequencer uses WSL `make`. This session repaired a WSL
startup failure with `[wsl2] memory=4GB` and `processors=4` in the previously
absent `C:\Users\assis\.wslconfig`, followed by WSL shutdown/startup. Evidence
is in `reports/spinal-hardware/wsl-repair.md`. Do not shut WSL down during a
running system generation. A preflight is:

```powershell
wsl -d Ubuntu -- bash -lc 'command -v make'
```

## Preserve the board software layout

The tested board is root on COM3 at 115200 baud, Angstrom Linux 4.5.0, Python2.7
and GCC4.9.3. The project is `/root/de10_gpu_platform`. Keep `software/`,
`scripts/` and `build/spinal-native-src/` at their repository-relative paths.
Prepare the native source with `scripts/prepare-spinal.ps1 -Kind native` and
transfer that owned tree and platform sources. Then on HPS:

```sh
cd /root/de10_gpu_platform
sh software/build_mmio.sh
sh software/spinal/build_native.sh
```

Do not replace a running helper executable in place. Stop its producer first,
or link a separate `.next` executable and atomically rename it. The helper's
Glide diagnostic log is replaced per capture, so continuous operation does not
grow it indefinitely.

## Quiesce, program and warm-boot

Stop the current producer before programming or standalone diagnostics. Verify
the PID file identifies this service before sending SIGINT:

```sh
cd /root/de10_gpu_platform/software
python -c 'import os,signal;p=int(open("spinal-server.pid").read());c=open("/proc/%d/cmdline"%p).read();assert "server.py" in c and "8081" in c;os.kill(p,signal.SIGINT)'
```

After reviewing the exact build hash, program FPGA position 2:

```powershell
Get-FileHash hardware/spinal_standard/output_files/Spinal_Standard_GPU.sof -Algorithm SHA256
& D:/Quartus/quartus/bin64/quartus_pgm.exe -c 'DE-SoC [USB-1]' -m JTAG -o 'p;D:\GPU_proj\hardware\spinal_standard\output_files\Spinal_Standard_GPU.sof@2'
& D:/Quartus/quartus/bin64/quartus_stp.exe -t D:/GPU_proj/hardware/spinal_standard/hps-reset.tcl --warm
```

Keep UART logging during the warm boot. The guarded reset script checks the
cable, FPGA ID and existing three-bit `RST` source, then pulses only warm reset.
Hot reconfiguration without HPS reset previously stalled HPS during the first
native render; it is not a proven operating sequence. Current U-Boot retains
the programmed FPGA image because its attempted SD `soc_system.rbf` is absent;
recheck this behavior if boot files change. No SD boot files were edited here.

## Re-establish LAN and audit this boot

Log in as root. Current temporary direct-link settings are:

```sh
ip link set dev eth0 down
ip link set dev eth0 address 02:de:10:00:03:01
ip link set dev eth0 up
ip addr add 169.254.170.29/16 dev eth0
cd /root/de10_gpu_platform
python software/spinal/audit_ddr.py --output ddr-audit.json
software/spinal/inspect_ddr_rules > ddr-rules.json
software/spinal/probe_sst
software/spinal/enable_ddr_ports --inspect
```

The laptop's direct-link address is `169.254.170.28/16`; display uses port 8081
because the existing gatord service owns 8080. The latest GPU2 boot reports
1 Gbit/s/full at both ends; an earlier GPU1 boot negotiated 10 Mbit/s. Recheck
`cat /sys/class/net/eth0/speed` and `duplex` after each boot and record the
actual speed with each measurement.
Restore these board settings after reboot; they are not persisted.
An interface down/up cycle was required on the latest boot despite correct
displayed MAC/IP and carrier; it restored packet reception. Keep the down step
before changing MAC. No PC network sharing or firewall changes are required.

Review audit success, the GPU2/ABI2 idle identity, full-bridge debug access,
and all valid SDR protection rules before enabling GPU DDR access. The tested
boot excludes all Linux allocator/reserved memblocks below `0x30000000`, while
the GPU uses `[0x3f400000,0x40000000)`. This is a current-boot exclusion, not a
persistent DT carveout. Audit again after boot/kernel/DT or ownership changes.
The one tested protection rule allows the full 1 GiB for all ports/IDs/security
states; the inspector never writes rule entries. Do not infer permission from
the port-reset register alone.

Once those checks pass and the generated HPS handoff still specifies mask
`0x1ff`, enable it through the idle/identity/lock-guarded helper:

```sh
software/spinal/enable_ddr_ports --enable
```

Do not modify live SDR geometry, protection rules, write-only L3 remap or boot
handoff registers to guess at a stall. The tested Linux sysfs bridge status
said enabled while actual SDR port reset was zero, so use the native readback.

## Capture and stream

[Native diagnostic instructions](../software/spinal/README.md) cover triangle,
both depth orders, solid/textured cubes, optional queued submission and durable
stage tracing. Capture raw files plus stderr JSON. On the laptop,
`scripts/check_spinal_frame.py` checks content; texture acceptance additionally
requires `--silhouette-reference` with the same-angle solid cube. Retain board
console/capture metadata separately to establish hardware provenance.

After accepting captures, start the native producer on HPS:

```sh
cd /root/de10_gpu_platform/software
nohup python server.py --renderer-helper spinal/spinal_capture --base 0xc0000000 --sidecar-base 0xff240000 --bind 0.0.0.0 --port 8081 --fps 10 --scene cube --angle 25 --angular-speed 30 </dev/null >spinal-server.log 2>&1 &
echo $! >spinal-server.pid
```

Open <http://169.254.170.29:8081/>. Native rendering and LFB readback produce
private RGB565 frames; the browser displays them without WebGL. Rotation/scene
controls are diagnostic only. Capture pause must finish before another GPU
owner starts. Latest-frame network buffering keeps slow clients independent
of rendering. GPU2 sequence advances by two per native capture; use
`scripts/measure_lan.py --sequence-step 2` when counting skipped captures.

The 10 FPS cap is deliberate and was measured on the current 1 Gbit/s link.
Use a lower cap if a subsequent boot negotiates a slower link. Keep initialization, begin-to-fence elapsed cycles
(including CPU gaps), pipeline occupancy, LFB copy, process wall time, delivered
FPS and send/ACK duration separate. Send/ACK time is a round trip with client
processing, not one-way display latency.
