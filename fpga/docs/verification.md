# Evidence and milestone gates

Only a real board capture through the HPS proves the FPGA→HPS→LAN path. A
snapshot replay proves the display software path; fake MMIO tests prove host
logic. Neither is board operation. Keep stdout, boot logs, Quartus reports,
bitstream SHA256 and capture JSON with each hardware run.

Run local regressions from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-deps.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tests.ps1 -Python C:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe
```

`tb_framebuffer.sv` checks all 76,800 pixels, busy/ready locking, rejected busy
restart/release, full-word commands, counters, read latency, back-to-back reads,
unpublished/out-of-range reads and reset. Its binary output is
`reports/simulated-frame.rgb565`, taken from the simulated Avalon read port.

`tb_rasterix_units.sv` instantiates the pinned upstream `Rasterizer` and
`TestFunc`. Two triangles form a 5×5 square under output stalls, with exact
coverage, no shared-edge overlap and correct vertically inverted framebuffer
indices. It tests 200 unsigned depth comparisons and enable behavior. This
does **not** verify a complete color/depth memory pipeline or satisfy the
hardware triangle/depth milestones. Full core Icarus elaboration encounters
unsupported empty `for` loop step syntax in upstream `PixelUtil.vh`; upstream
uses Verilator. That simulator limitation does not establish a Quartus blocker.

The Python tests exercise host ownership and protocol delivery. The streaming
test compares the entire RTL-produced dump against WebSocket payload bytes,
and checks that a stalled consumer does not prevent the producer advancing.

| Gate | Required evidence |
|---|---|
| 1: build/program | Exact Standard part, successful fitter/assembler, timing review, programmer success and SHA256 |
| 2: HPS registers | Boot model/kernel/image, bridge state and actual GPU1/ABI register read |
| 3: pattern retrieval | Host `--check-pattern`, 153600 bytes, source hardware and sequence/cycle metrics |
| 4: LAN frame | Laptop browser at board IP, source hardware, screenshot and matching sequence |
| 5: triangle | Command stream reaches FPGA; pixel comparison of retrieved frame |
| 6: depth | Reverse submission order of overlapping triangles yields same visible result; inspect Z/color |
| 7: cubes | Rotating cube then texture coordinate/checkerboard diagnostic through hardware pipeline |
| 8: continuous | Record render cycles, capture FPS, browser FPS, CPU, network rates and slow-consumer behavior |

Stop at the first failing hardware gate. For gate 6, test near/far equality,
clear values, disabled depth, out-of-viewport fragments and overflow boundaries.
For the future memory bridge, randomize AXI/Avalon backpressure and check byte
enables, read ordering, response errors and fences before trusting swaps.

Raw RGB565 costs 153600 bytes/frame: 18.432 Mbit/s at 15 FPS and 36.864 Mbit/s
at 30 FPS before network framing. These are arithmetic requirements, not measured
throughput. Use the browser metrics for delivered FPS, `/metrics` for producer
capture rate and cycle-based render time; WS ACK time includes browser work and
network round trip. Compare MJPEG on the HPS with the same scene/rate if raw
transfer or client conversion becomes limiting. Keep latest-only publication.
