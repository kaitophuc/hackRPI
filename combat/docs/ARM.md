# ARM and RasterIX integration

These are integration instructions. No ARM executable or RasterIX library was built or run in this environment. The delivered EXE is the Windows desktop build. The GPU team must first supply the target OS/architecture, RasterIX commit/configuration, context/bus connector, graphics memory budget and streaming/input host.

## Portable game host

The core uses standard C# and avoids Windows APIs. `Desktop.cs` is excluded from the modern .NET headless project. With a .NET 8 SDK and appropriate runtime packs installed:

```sh
dotnet build src/Flighting.Headless.csproj -c Release
dotnet publish src/Flighting.Headless.csproj -c Release -r linux-arm --self-contained true -o publish/linux-arm
# For a 64-bit board use -r linux-arm64 and a different output directory.
```

On the target, install the published runtime's OS prerequisites and run:

```sh
./FlightingSimulatorGame --self-test
./FlightingSimulatorGame --headless --scripted --ticks 600 --no-hud --out arm-software.ppm
```

The board needs a supported Linux userspace/runtime; bare-metal or an unsupported libc requires a separate native platform port. The project is not a claim that every ARM board supports .NET. Game simulation and scene definitions are separated from the host and renderer to make such a port reviewable.

## Native RasterIX bridge

The upstream [RasterIX project](https://github.com/ToNi3141/RasterIX) supplies FPGA and software rasterization paths. Select and record a concrete commit. Follow that revision's build instructions; no guessed RasterIX ARM preset is hardcoded here. RasterIX is external and has its own license and dependencies.

Supply a C/C++ host file implementing these hooks from `native/flighting_bridge.h`:

1. `fg_platform_open(w,h)`: create and bind the selected RasterIX software or FPGA context. Use a fresh dedicated context with default depth range/clear-depth state.
2. `fg_platform_get_proc(name)`: resolve the exact RasterIX GL entry points. On Windows, core exports may need direct DLL lookup as well as context-specific lookup. Do not resolve to the system desktop GL driver when reporting RasterIX validation.
3. `fg_platform_backend_name()`: return a stable UTF-8/ASCII identifier with RasterIX commit, software/RTL/FPGA mode, pixel/depth format and relevant configuration.
4. `fg_platform_present(rgba,w,h)`: deliver the top-down image or copy it into the platform framebuffer/streamer. Report failures; instrument delivery separately from rendering.
5. `fg_platform_close()`: release context and platform resources.

With the target compiler/sysroot, its CMake toolchain file and the selected RasterIX libraries:

```sh
cmake -S native -B build/arm-bridge \
  -DCMAKE_TOOLCHAIN_FILE=/absolute/path/to/gpu-team-arm-toolchain.cmake \
  -DFLIGHTING_PLATFORM_SOURCE=/absolute/path/to/gpu-team/host_rasterix.c \
  -DFLIGHTING_PLATFORM_LIBRARIES="/absolute/path/to/selected/librasterix.a"
cmake --build build/arm-bridge --parallel
```

Library names and transitive link dependencies come from the selected RasterIX build. Put `libflighting_rasterix_bridge.so` beside the published game host (or in the target's configured library search path). Managed and native bitness/architecture must match. On Windows use `flighting_rasterix_bridge.dll`; the upstream Windows software preset described in its README is 32-bit, so a matching 32-bit process/bridge is required. The delivered managed EXE is AnyCPU and normally runs as 64-bit on this machine; rebuild it with `/platform:x86` to load a 32-bit bridge.

The included C glue uses fixed-function GL, RGBA8 upload and blocking readback. If that revision does not expose a function or its bus connector uses another readback path, the GPU team must adapt the bridge and document the contract change. Missing features must fail; never route compatibility tests to the system GL implementation.

```sh
./FlightingSimulatorGame --backend rasterix --suite --capture captures/rasterix-suite
./FlightingSimulatorGame --backend rasterix --headless --replay tests/sample-flight.csv --no-hud --out rasterix-flight.ppm
./FlightingSimulatorGame --backend rasterix --render-capture captures/software/scene-4/frame.json --out rasterix-texture.ppm
```

The first command exercises the same seven scenes through the selected RasterIX path. The last isolates rasterization from gameplay by using identical captured clip-space vertices, camera, states and assets.

## Browser input and continuous platform loop

Connect the GPU team's browser adapter to the proposed loopback UDP contract in [CONTRACT.md](CONTRACT.md). Then:

```sh
./FlightingSimulatorGame --backend rasterix --headless --realtime --input-udp 5522 --ticks 0 --scene 6 --width 640 --height 400 --complexity 18 --out final-frame.ppm
```

This loop renders continuously, advances fixed-step simulation only with fresh connected input, and stops on Ctrl+C. `fg_platform_present` owns platform display/stream delivery. The default software backend can run this loop without a board to test the adapter, though it only delivers a final PPM unless a separate display/stream host is attached. No browser transport is bundled. For finite integration tests use `--ticks 600`; the tick limit counts simulated ticks, so a disconnected source pauses rather than ending the run.

For combat, the proposed input bitmask adds held fire (4) and game-over restart (8). Finite headless runs also end at game over; unlimited `--ticks 0` hosts keep delivering the game-over frame and can consume a restart packet. The browser/platform team must implement the corresponding UI/control mapping. The desktop Replay button does not itself create a browser-input service.

## Required board evidence

Record toolchain, CPU/runtime, RasterIX commit/config, hardware revision, resolution, scene complexity, framebuffer formats, every scene's output, exact replay/seed, input timeout/focus tests, texture-upload failures, native error logs and stage timings. Run the image comparison workflow with an agreed quantization/edge tolerance. Record GPU execution, frame readback, streamer throughput and browser display rate separately. Only then update the pending compatibility/board rows in `VALIDATION.md`.
