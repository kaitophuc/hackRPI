# LAN display transport

`software/server.py` supports Python 2.7 on the existing Angstrom SD image and
Python 3 on modern Linux, using only the standard library. It serves static HTML plus
a binary WebSocket at `/ws`. The browser converts received RGB565 pixels with
`putImageData`; it does not render geometry or use WebGL. `/metrics` exposes host
JSON diagnostics. Diagnostic scene controls honestly show the integrated pattern
or the scenes explicitly supplied by a native GPU2 renderer adapter.

## Run on the HPS

After verifying the generated peripheral address and booting matching HPS bridge
configuration (see `hps.md`), from the repository root:

```sh
sh software/build_mmio.sh
sudo python3 software/server.py --device --base 0xff240000 --bind 0.0.0.0 --port 8080 --fps 15
```

For the board's original Python 2.7 environment, build the native capture program
with its installed GCC and run the same server implementation:

```sh
sh software/build_capture.sh
python software/server.py --device --base 0xff240000 --bind 0.0.0.0 --port 8081 --fps 5
```

`legacy_host.py` invokes the adjacent native `capture` program once per frame and
validates its raw output and JSON metadata. The C program uses bounded MMIO
polling and releases the framebuffer before writing to the Python pipe. The
subprocess has an additional deadline. Its process and pipe overhead is included
in host capture time. Python 3 keeps the direct native MMIO accessor backend.
This compatibility path does not require replacing Linux.

To enable the optional shared JPEG encoder, first build against the board's
installed libjpeg, then add the explicit helper option:

```sh
sh software/build_jpeg.sh
python software/server.py --device --base 0xff240000 --bind 0.0.0.0 --port 8081 --fps 5 \
  --jpeg-helper /root/GPU_proj/software/jpeg_benchmark --jpeg-quality 75
```

Use the actual absolute location of the uploaded tree. Select **MJPEG** on the
page after connection. Switching transports does not reconfigure the renderer.
Without `--jpeg-helper`, the MJPEG option is disabled and the encoder costs no CPU.
With it, an independent worker encodes each newest snapshot at most once, sharing
one immutable JPEG among all consumers. If encoding falls behind, the worker
skips intermediate snapshots; capture never waits for encoding or clients.

The base matches this project's generated CPU address map; check it again after
hardware changes. Browse to `http://BOARD_LAN_IP:8080/`. No external monitor is
needed. The producer is the only MMIO owner and releases each framebuffer after
copying into immutable HPS memory, before any network consumer sees it.

For an explicitly offline test with a previously captured raw RGB565 file:

```sh
python3 software/server.py --snapshot frame.rgb565 --width 320 --height 240 --bind 127.0.0.1 --port 8080
```

Snapshot mode is prominently marked on the page and cannot establish that FPGA
generation, HPS bridges, or board networking work. The server is intended for a
trusted LAN, with no authentication/TLS; do not expose its port to the Internet.

## Bounded buffering and controls

The producer maintains exactly one latest immutable snapshot. Each of at most
four WebSocket consumers may have one frame awaiting an application-level ACK.
The client sends its ACK after decoding and updating the canvas. The next send
reads the latest snapshot, skipping all intermediate captures. A blocked socket
or missing ACK is disconnected after a five-second operation/deadline timeout.
No client locks the producer or keeps the FPGA framebuffer owned. Ordinary HTTP
handler threads are bounded to twelve; every connection has a five-second socket
timeout. Small control messages are limited to 4096 bytes and masked WebSocket
frames are required. Browser controls are same-origin only. Pause stops capture,
not merely browser consumption; cube rotation remains disabled until available.

The four-client limit is shared with MJPEG. `/mjpeg-session` creates a short-lived
random token; `/stream.mjpg?session=TOKEN` serves standard multipart JPEG parts
with `Content-Length`, `X-Sequence` and `X-Source` headers. The page reads each part
with Fetch, decodes it to the canvas, then POSTs `{session, sequence}` to
`/mjpeg-ack`. There is at most one unacknowledged JPEG per connection. Its next
part is the newest encoded snapshot, so neither TCP nor browser buffering can
queue stale frames. Missing ACKs close the stream after five seconds. An ordinary
`<img>` client does not send these ACKs and is therefore not a supported continuous
consumer. Pending session creation is bounded to sixteen records and expires
after ten seconds; active display sockets share the existing four slots.
`/control` accepts the same small diagnostic controls used over WebSocket.

## Transport choice and measurement

Initial choice: raw RGB565 WebSocket, provisionally. At 320x240, each frame has
153600 pixel bytes plus a 24-byte header. Payload at 15 FPS is 2.304 MB/s (18.432
Mbit/s); at 30 FPS it is 4.608 MB/s (36.864 Mbit/s). These are arithmetic budgets,
not measured board throughput. Raw mode avoids JPEG dependencies and encoding
CPU work, and preserves exact pixels for hardware correctness checks. It still
costs HPS copying and Python socket framing; browser RGB expansion has CPU cost.

The initial raw path is now hardware-tested: the pattern stream delivered
5.024 FPS at 6.209 Mbit/s raw payload with a 5 FPS cap, and the laptop browser
displayed 4.982 FPS with zero pixel mismatches. Send-to-ACK averaged 133.449 ms;
this includes network transfer and client processing, not one-way latency.
See `reports/lan-measurement.json` and `reports/browser-measurement.json` for the
conditions and separate measurements. These are pattern tests, not 3D throughput.

MJPEG trades lossy pixels and encode CPU time for fewer LAN bytes. The optional
path uses the installed CPU libjpeg; no hardware encoder is assumed. Its page
metrics distinguish RGB conversion, JPEG encoding CPU/wall time, and total helper
wall time including subprocess/pipes. A lower JPEG byte count alone does not
establish lower end-to-end latency. Keep raw WS for exact rendering checks and
compare both paths under the same cap, scene and negotiated Ethernet speed.

For capture-only timings first run `sudo python3 software/benchmark.py --base
0xff240000 --frames 100 --output capture-benchmark.json`. This validates the
first and last pattern, summarizes render/copy/capture and packet preparation
costs, and records process CPU time. It does not measure browser delivery.

For each 60-second run record scene, render size, clock, CPU model/governor,
network link speed, browser, client count and FPS cap. Save `/metrics` at start
and end, monitor server CPU with `pidstat -u -r -p PID 1 60`, and record network
bytes using `ip -s link show eth0`. The page reports:

* FPGA render milliseconds from its cycle counter and clock (inverse is isolated
  render FPS, not continuous throughput).
* Host capture FPS and per-frame MMIO copy/capture milliseconds.
* Browser displayed FPS and acknowledged frame count.
* Send-to-ACK round-trip milliseconds, including transfer, canvas decoding and
  return ACK. This is not one-way latency and does not include time before send.
* Packet preparation and socket send milliseconds plus wire bytes per frame.
  Socket send completion includes kernel buffering, not proof of browser receipt.

For the MJPEG comparison, record the runtime `jpeg_lib_version` from the native
helper, fixed quality, CPU load, transmitted bytes, browser displayed FPS and
send-to-ACK timing under the same LAN conditions. `jpeg_benchmark --stdin
--stdout` accepts exactly one RGB565 frame on stdin, emits one JPEG on stdout and
one JSON measurement on stderr; its old file/30-frame benchmark mode is retained.
WebRTC is not needed for this bring-up path.

## Explicit native GPU2 renderer adapter

The native adapter implements the shared `spinal-interface.md` contract. GPU2
triangle, serialized depth and solid/textured-cube captures pass on the board,
and the raw LAN path delivers about 10 FPS. See `reports/spinal-3d-result.md` for
the loaded bitstream and separate source/simulation/hardware evidence. Follow
`spinal-standard-bringup.md` for programming, reboot and DDR audit; do not run
the adapter against GPU1 or assume a past boot's memory audit still applies.

```sh
python software/server.py --renderer-helper /root/de10_gpu_platform/software/spinal/spinal_capture \
  --base 0xc0000000 --sidecar-base 0xff240000 --scene triangle \
  --angle 0 --angular-speed 0 --port 8081 --fps 5
```

The helper exclusively renders, fences, copies and releases the GPU before
output. The adapter passes explicit scene, angle and depth-order flags, validates
the helper's renderer/scene metadata, and has a separate 15-second process
deadline to allow native driver initialization. Its frame timing is labeled
**begin-to-fence including CPU submission gaps**, rather than isolated raster FPS.
Per-process initialization is included in host capture wall time. Cube rotation
only changes the native helper's angle input; the browser never draws geometry.
`--angular-speed 0` gives deterministic checks, `--depth-order near-first` or
`far-first` selects the overlap submission order. The adapter never silently
falls back to the GPU1 pattern peripheral or an offline software renderer.
