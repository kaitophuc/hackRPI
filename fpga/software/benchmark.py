#!/usr/bin/env python3
"""Capture timing diagnostics; a rate cap or offline replay is not GPU throughput."""
import argparse
import json
from pathlib import Path
import statistics
import time

from host import Device, Snapshot, check_pattern


def summary(values):
    ordered = sorted(values)
    return {"mean": statistics.mean(ordered), "median": statistics.median(ordered),
            "p95": ordered[min(len(ordered) - 1, int((len(ordered) - 1) * .95))],
            "max": ordered[-1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--base', type=lambda value: int(value, 0))
    source.add_argument('--snapshot', type=Path, help='explicit OFFLINE replay')
    parser.add_argument('--span', type=lambda value: int(value, 0), default=0x27000)
    parser.add_argument('--width', type=int, default=320)
    parser.add_argument('--height', type=int, default=240)
    parser.add_argument('--frames', type=int, default=100)
    parser.add_argument('--output', type=Path, default=Path('capture-benchmark.json'))
    args = parser.parse_args()
    if not 1 <= args.frames <= 100000:
        parser.error('--frames must be 1..100000')
    backend = (Device(args.base, args.span) if args.base is not None else
               Snapshot(args.snapshot, args.width, args.height))
    copies, captures, renders, prepare = [], [], [], []
    cpu_start, wall_start = time.process_time(), time.monotonic()
    with backend:
        first = backend.capture_pattern()
        check_pattern(first)  # Validate before measuring; recover any prior ready frame.
        for _ in range(args.frames):
            frame = backend.capture_pattern()
            copies.append(frame.copy_seconds * 1000)
            captures.append(frame.capture_seconds * 1000)
            if frame.source == 'hardware' and frame.clock_hz:
                renders.append(frame.render_seconds * 1000)
            started = time.monotonic()
            packet = frame.to_wire()
            prepare.append((time.monotonic() - started) * 1000)
        check_pattern(frame)
    wall = time.monotonic() - wall_start
    cpu = time.process_time() - cpu_start
    result = dict(source=frame.source, measured_frames=args.frames,
                  wall_seconds_including_validation=wall, process_cpu_seconds=cpu,
                  width=frame.width, height=frame.height, raw_frame_bytes=len(frame.pixels),
                  framed_bytes=len(packet), last_sequence=frame.sequence,
                  copy_ms=summary(copies), capture_ms=summary(captures),
                  packet_prepare_ms=summary(prepare),
                  render_ms=summary(renders) if renders else None,
                  capture_fps=(1000 / statistics.mean(captures)
                               if sum(captures) else None),
                  render_fps=(1000 / statistics.mean(renders)
                              if sum(renders) else None),
                  browser_delivered_fps=None,
                  note='No network/client measurement here; browser reports displayed FPS and ACK RTT')
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
