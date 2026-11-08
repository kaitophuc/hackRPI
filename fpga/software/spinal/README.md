# Native SpinalVoodoo diagnostics

This producer uses the pinned SpinalVoodoo ARM Glide backend. CPU code performs
vertex transforms and triangle setup; the FPGA performs coverage, depth testing,
color writes and texture sampling. No software framebuffer renderer is linked.
The prepared driver is a build copy; upstream stays clean.

Prepare on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-spinal.ps1 -Kind native
```

This exports commit `92c56afa0e98763ccd794cd39512cad2822bd86e` to
`build/spinal-native-src` and applies `patches/spinal/glide-headless.patch`.
On an ARM HPS with GCC, Make and libc development files, preserve the relative
directories from the repository or the prepared bundle and run:

```sh
sh software/spinal/build_native.sh
```

An optional first argument specifies another absolute prepared-source root.
The build makes the static native Glide library, without X11, then links
`software/spinal/spinal_capture`. The Cortex-A9 command uses `-march=armv7-a`.
Glide uses its existing C triangle-setup implementation; no x86 assembly, SDL,
DOSBox, game data, or window server is required.

Do not run this against the pattern image. Root must first verify the Standard
GPU2 bitstream, generated address maps, reserved upper-DDR ownership and ordered
memory backend. The native producer refuses writes unless the sidecar identifies
as GPU2 (`0x47505532`), ABI 2, 320x240 RGB565.

```sh
software/spinal/spinal_capture --base 0xc0000000 --sidecar-base 0xff240000 \
  --scene triangle --output triangle.rgb565
software/spinal/spinal_capture --base 0xc0000000 --sidecar-base 0xff240000 \
  --scene depth --depth-order far-first --output depth-far-first.rgb565
software/spinal/spinal_capture --base 0xc0000000 --sidecar-base 0xff240000 \
  --scene depth --depth-order near-first --output depth-near-first.rgb565
cmp depth-far-first.rgb565 depth-near-first.rgb565
software/spinal/spinal_capture --base 0xc0000000 --sidecar-base 0xff240000 \
  --scene cube --angle 25 --output cube.rgb565
software/spinal/spinal_capture --base 0xc0000000 --sidecar-base 0xff240000 \
  --scene textured-cube --angle 25 --output textured-cube.rgb565
```

Depth diagnostics use inverse-depth GREATER with a zero clear: a near red
triangle (`ooz=50000`) and far blue triangle (`ooz=20000`). Center pixel
(160,120) must be red, and changing submission order must not change any pixels.
The supported port serializes primitive submission: every triangle passes through
one wrapper that calls `grDrawTriangle` then `grSstIdle`; the initial buffer
clear also waits for idle before drawing or changing color. This protects live
render state while the FIFO/state synchronization path is under investigation.
It applies to both depth orders and every cube triangle. Idle does not replace
the final explicit GPU2 publication fence or establish DDR completion by itself.
Reported begin-to-final-fence timing includes these CPU waits; these diagnostic
scenes do not establish a maximum pipelined rendering rate.
For explicit FIFO/state-ordering regression only, `--queued-primitives` bypasses
the per-triangle and initial-clear idle waits, reproducing back-to-back command
submission. The default remains serialized.

**This queued diagnostic still fails on the accepted E1366086 hardware image;
do not use it for rendering or infer safety from the simulation guard test.**

The verified triangle/depth/cube/textured-cube results use the default path.
Success metadata identifies
`submission_mode` as `serialized` or `queued`; pixel/depth expectations and the
final publication fence remain unchanged in both modes. Compare both depth
submission orders in queued mode when validating the hardware ordering repair.
The single white triangle has vertices (40,200), (160,30), (280,200) over a black
background; safe interior and exterior samples are (160,120) and (10,10).
Dithering, blending, fog and chromakey are explicitly disabled for deterministic
solid-color expectations. Cubes have 12 triangles with per-face solid colors or
a generated 64x64 white/blue checkerboard; texture coordinates use perspective
division through Glide/TMU parameters. The explicit angle is in degrees.

The helper acquires the same advisory lock as the pattern producer. It renders
to the backbuffer and never swaps, so retrace and HDMI are not prerequisites.
It requests an explicit sidecar flush/fence, performs full ordered native
`grLfbReadRegion` readback into private HPS RAM, checks sequence/ready stability,
then releases before output. It never directly copies raw HPS DDR. GPU2 ready
means safe for ordered LFB readback; it is not a claim of global DDR commitment
across independent masters. See `docs/spinal-interface.md`.

`--stdout` emits only 153600 raw little-endian RGB565 bytes. One success JSON
object goes to stderr. Glide's diagnostics go to `/tmp/gpu-spinal-glide.log`,
overridden by `--log FILE`; failures return nonzero and identify the log path.
Each capture replaces that diagnostic log, retaining the latest attempt and
avoiding unbounded growth during continuous streaming. Use distinct `--log`
paths when retaining multiple standalone diagnostic attempts.
For hang diagnosis, add `--progress /root/de10_gpu_platform/capture.progress`.
This optional file receives append-only monotonic-time stage markers before
and after the first SST read, Glide initialization/query/select/window setup,
idle/fence operations, state setup/draw, LFB readback, release and shutdown.
Each marker is written and `fsync`ed before execution continues, so the last
durable marker can identify a stalled stage after recovery. Pre-create and
sync the file before an experiment when recovery evidence matters. Progress
open/write/sync failures stop capture; markers never enter raw stdout or JSON.
The filesystem synchronization overhead affects all reported diagnostic
timings and can dominate them. Omit `--progress` for performance measurements.
The `--timeout` default of two seconds applies to each explicit fence poll.
An outer process timeout should also allow for driver initialization and LFB
copy; a stalled physical bus cannot be recovered by a userspace polling limit.

`render_cycles` is **begin-to-fence elapsed FPGA cycles, including CPU command
submission gaps**, not isolated raster throughput. `pipeline_busy_cycles` is
separate occupancy instrumentation. `copy_seconds` covers LFB readback;
`capture_seconds` covers begin/draw/fence/readback/release. Driver setup is
reported separately as `initialization_seconds`. The current one-shot helper
reinitializes Glide for each process; adapter process wall time must include it.
Do not report a streaming renderer rate by dividing only the last frame's cycles.

The headless patch selects existing no-op X11 presenter functions, removes X11
linking and ADV7513 initialization, and describes the known GPU2 one-TMU/4 MiB
usable texture configuration instead of destructive legacy memory-discovery
render/read probes before a fence. It does not replace the actual rasterizer.
The producer verifies GPU2 before using this fixed configuration and sets
`SST_FBIMEM_SIZE=4`, `SST_TMUMEM_SIZE=4`.
The headless video setup also programs the actual target stride and surface
offset instead of leaving the upstream initialization's 640x480 layout:
320 pixels per row and 38 four-KiB units (155648 bytes) per RGB565 surface.
The native LFB aperture still uses its own virtual row addressing; only the
returned CPU snapshot is tightly packed at 640 bytes/row.

Original producer/helper code is MIT. Imported native API code retains the
3DFX Glide source license in `build/spinal-native-src/emu/glide/LICENSE` and
`emu/glide/glide2x/glide_license.txt`, plus individual source notices.
The selected FPGA core's root license is CERN-OHL-W-2.0; that does not relicense
the imported API. Preserve notices and ship the pinned source plus patches.

Status: native build and GPU2 diagnostic execution succeeded on the actual HPS
with GCC 4.9.3. Triangle, serialized depth and solid-cube captures pass, and the
GPU2 LAN service replaces the stopped GPU1 producer. The imported build needs
gnu99 and explicit archive-directory creation; both are in `build_native.sh`.
The timing-clean E1366086 image fixes texture cold misses: both textured-cube
silhouettes pass with zero holes. Queued submission still fails and is diagnostic
only. All ten platform regressions pass. See `reports/spinal-3d-result.md` for
current hardware evidence and limitations.

## DDR bring-up guard (current boot only)

`audit_ddr.py` checks the live Linux memory and reserved memblocks, the loaded
kernel configuration, DT owners and process mappings before using the upper
12 MiB GPU pool. It also reads the actual SDR port-reset register. The current
kernel has HIGHMEM disabled and keeps all allocator/reserved memblocks below
0x30000000. A successful audit is specific to this boot; it is not a permanent
device-tree reservation and must be repeated after boot/image changes.

Build `libgpu_mmio.so` with `software/build_mmio.sh` for the audit. After a
reviewed, timing-checked GPU2 image is loaded and the old producer is stopped:

```sh
python software/spinal/audit_ddr.py --output /root/de10_gpu_platform/ddr-audit.json
software/spinal/enable_ddr_ports --inspect
software/spinal/inspect_ddr_rules > /root/de10_gpu_platform/ddr-rules.json
# Only after reviewing a successful audit and the generated HPS handoff:
software/spinal/enable_ddr_ports --enable
```

The helper is built by `build_native.sh`. It checks idle GPU2/ABI2 under the
producer lock, then enables exactly the generated `F2SDRAM_RESET_PORT_USED`
mask 0x1ff at SDR `fpgaportrst` (0xffc25080), preserving other bits and verifying
readback through the ordered native accessor. Recheck this mask if Qsys changes.
The current old boot image reports fpga2sdram enabled despite register value0;
that sysfs status alone is insufficient. The helper does not change DDR timings,
Linux boot files or system-manager handoff registers. It cannot replace the
audit or establish exclusive ownership against unrelated raw-memory software.

The protection inspector issues only the documented read-rule command to the
SDR table selector, restores its initial selection and leaves table entries
unchanged. Review all valid rules: the current boot has one allow rule covering
0..1 GiB for all ports/IDs and both security states, including the GPU pool.
The default is deny, so this rule review is required even when exclusion passes.

Once captures are retrieved, `scripts/check_spinal_frame.py` checks scene
invariants. Depth checking requires both submission-order snapshots via
`--compare`; hardware provenance still comes from the capture/console evidence.
