# CPU JPEG transport evaluation

`software/jpeg_benchmark.c` is an offline encoder benchmark operating on a
captured little-endian RGB565 file. It does not access FPGA registers, render
scenes, serve MJPEG, measure a network path, or implement hardware encoding.

The existing hardware test-pattern WebSocket path delivered 5.0236 FPS and
6.2085 Mbps raw payload over the observed 10 Mbps direct Ethernet link.
Its socket consumer measured 133.45 ms mean send-to-ACK round trip; a separate
real browser showed approximately 4.98 FPS and zero mismatched pixels.
These measurements used a configured approximately 5 FPS capture rate, so
they are not an unrestricted maximum-throughput result. The roughly 40 ms
legacy adapter capture and 15.6 ms native MMIO copy are distinct from the
0.768 ms FPGA pattern-generation time. See `reports/lan-measurement.json`
and `reports/browser-measurement.json`.

Raw RGB565 requires 153600 bytes/frame before protocol overhead. At 30 FPS
that is 36.864 Mbps, which exceeds the observed physical link speed. JPEG is
worth measuring because it reduces bytes at the cost of CPU work and lossy
pixels. An MJPEG transport cannot be selected on byte savings alone: actual
delivered FPS, CPU consumption and latency would also need a real streaming
implementation and browser test.

Build and run on the HPS using its existing libjpeg headers and library:

```sh
cc -std=c99 -O2 -Wall -Wextra -Werror jpeg_benchmark.c -o jpeg_benchmark -ljpeg -lrt
./jpeg_benchmark frame.rgb565 --frames 30 --quality 75 --output frame-q75.jpg
```

Optional `--width` and `--height` default to 320 and 240. Input length must
match exactly `width * height * 2`; truncated or padded files fail. Quality
accepts 1 through 100, defaults to 75 and uses baseline-compatible quantization.
Default libjpeg sampling is retained; optimize-coding is disabled. RGB channels
are expanded by bit replication from 5/6/5 to 8/8/8 before compression.

The implementation uses a portable custom in-memory destination manager rather
than `jpeg_mem_dest`, so older libjpeg versions can compile it. Destination
storage grows when needed. Encoder setup and initial input/RGB allocations are
outside timing; each iteration includes fresh RGB565 conversion, compression
start/scanline/finish, and any destination growth. No warm-up iteration is
discarded. The optional first JPEG is written after its timer stops; disk I/O
is excluded. The same captured input is encoded repeatedly, so this measures
one scene, not a distribution of game content.

One JSON line on stdout reports:

| Field | Meaning |
|---|---|
| `mean_encode_ms` | Mean wall time for RGB565 conversion plus JPEG encoding |
| `cpu_ms` | Mean process CPU time over the same region |
| `rgb_conversion_ms` | Mean wall time for conversion and timer overhead |
| `jpeg_ms` | Mean wall time for in-memory JPEG encoding |
| `bytes` | Mean encoded bytes/frame |
| `min_bytes`, `max_bytes` | Encoded size range across repetitions |
| `frames`, `quality`, `jpeg_lib_version` | Benchmark configuration/library ABI |
| `source` | Always `offline-rgb565-jpeg-benchmark` |

To compare against raw transport, compute compressed payload Mbps as
`bytes * delivered_fps * 8 / 1000000` and CPU fraction for encoding as
`cpu_ms * delivered_fps / 1000`. These calculations exclude TCP/HTTP/MJPEG
headers, socket processing, capture, and browser decode/display. Do not infer
one-way latency from an ACK round trip. Keep the verified lossless raw stream
as the current transport until JPEG streaming has its own measured evidence.

## Measured solid-cube encoder result

The native encoder ran on the actual HPS against the accepted hardware
`cube-25.rgb565` (SHA256
`88822dd737e21ef38fb60269487340dc6a6a1708e38a1950105e1c59cb103117`).
Thirty repeated encodes at quality 75, libjpeg ABI 80, produced 4,100 bytes per
frame. Mean RGB conversion plus encoding was 7.145 ms wall / 7.015 ms process
CPU; conversion was 1.527 ms and JPEG work 5.619 ms. File I/O was excluded.
See [raw benchmark JSON](../reports/spinal-cube-jpeg-benchmark.json).

At five frames/second, those JPEG payload bytes would be 0.164 Mbit/s and the
measured encoder region alone would consume about 3.5% of one core. These are
derived budgets, excluding helper startup/pipes, capture, sockets and display.
They are not measured MJPEG delivery or latency. The real raw rotating-cube
stream delivered 4.993 FPS with zero skipped captures; its surrounding
12-second observation used 30.567% of one HPS core for server plus render
helpers, excluding unrelated processes and system-wide IRQ work.

Raw WebSocket remains the selected verified mode: it fits the current link at
the selected cap and preserves exact pixels for hardware diagnostics.
JPEG is an implemented candidate for a higher-rate display after its own
end-to-end measurement. A solid cube's compressibility and CPU time must not
be extrapolated to a textured cube or future game scenes. A live GPU2 recheck
now reports 1 Gbit/s/full on HPS and Windows; the 10 Mbit/s condition in the
historical GPU1 paragraph above must not be assumed for later runs. A subsequent
raw solid-cube run at a 10 FPS cap delivered 10.009 FPS / 12.250 Mbit/s with
zero skipped captures and 66.273% of one core for server plus render helpers;
see `reports/spinal-rotating-10fps-lan.json` and `reports/spinal-cpu-10fps.json`.
