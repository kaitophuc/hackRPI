#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
cd "$root"
python combat/board/stop_service.py
python combat/board/stop_diagnostics.py
python fpga/software/spinal/audit_ddr.py > current-ddr-audit.json
mkdir -p /dev/shm/hackrpi-game
chmod 700 /dev/shm/hackrpi-game
rm -f /dev/shm/hackrpi-game/stop /dev/shm/hackrpi-game/frame.bin /dev/shm/hackrpi-game/frame.bin.next
export FLIGHTING_FRAME_FILE=/dev/shm/hackrpi-game/frame.bin
export FLIGHTING_STOP_FILE=/dev/shm/hackrpi-game/stop
export SPINAL_WBUFFER=1
# The legacy bridge remains serialized; the validated pipeline uses its own
# queued submission with three synchronization commands per triangle.
export SPINAL_BATCH_TEST=${SPINAL_BATCH_TEST:-0}
export FLIGHTING_PIPELINE=${FLIGHTING_PIPELINE:-1}
export FLIGHTING_PACKED_REUSE=${FLIGHTING_PACKED_REUSE:-1}
export FLIGHTING_CITY_XY_CACHE=${FLIGHTING_CITY_XY_CACHE:-1}
export SPINAL_CACHE_COLORS=${SPINAL_CACHE_COLORS:-1}
export SPINAL_COVERAGE_REJECT=${SPINAL_COVERAGE_REJECT:-1}
# Avoid readback wakeup preemption of the GPU submission thread.
export SPINAL_READBACK_BATCH=${SPINAL_READBACK_BATCH:-1}
# Constant-combiner and fixed-register prototypes did not show a useful gain.
export SPINAL_CONSTANT_COLORS=0
export SPINAL_FAST_FLAT_SETUP=0
nohup python combat/board/arduino_usb.py --frame-yield-ms "${HACKRPI_SENSOR_FRAME_YIELD_MS:-150}" --snapshot /dev/shm/hackrpi-game/sensor.json </dev/null >sensor.log 2>&1 &
echo $! >sensor.pid
nohup sh combat/board/run_game.sh --backend spinal --headless --realtime --input-udp 5522 --sensor-file /dev/shm/hackrpi-game/sensor.json --ticks 0 --scene 6 --complexity 18 --scenery-range 1 --quality low --fps 30 --out last-frame.ppm </dev/null >game.log 2>&1 &
echo $! >game.pid
nohup python fpga/software/server.py --game-frame "$FLIGHTING_FRAME_FILE" --game-input-port 5522 --bind 0.0.0.0 --port 8081 --fps 60 </dev/null >web.log 2>&1 &
echo $! >web.pid
echo 'AERO FPGA game: http://169.254.170.29:8081/'
