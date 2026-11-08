#!/usr/bin/env python3
"""DE10-Standard framebuffer bring-up API. No software scene renderer.

Use a verified physical address from the generated hardware address map.
The real backend is Linux-only and requires an enabled, clocked FPGA bridge.
"""
import argparse
import ctypes
from dataclasses import dataclass
import json
import mmap
import os
from pathlib import Path
import struct
import sys
import time

GPU_ID = 0x47505531
ABI_VERSION = 1
FRAME_OFFSET = 0x1000
DEFAULT_SPAN = 0x27000
WIRE_HEADER = struct.Struct('<4sIIIII')


@dataclass(frozen=True)
class Frame:
    sequence: int
    width: int
    height: int
    pixels: bytes
    render_cycles: int = 0
    clock_hz: int = 0
    copy_seconds: float = 0.0
    capture_seconds: float = 0.0
    source: str = 'hardware'

    def __post_init__(self):
        validate_geometry(self.width, self.height, self.width * 2, 1)
        if not isinstance(self.pixels, bytes) or len(self.pixels) != self.width * self.height * 2:
            raise ValueError('pixels must be an immutable, tightly packed RGB565 byte buffer')

    @property
    def render_seconds(self):
        return self.render_cycles / self.clock_hz if self.clock_hz else 0.0

    def to_wire(self):
        return WIRE_HEADER.pack(b'GPU1', self.sequence & 0xffffffff,
                                self.width, self.height, 1, len(self.pixels)) + self.pixels

    def metrics(self):
        return dict(source=self.source, sequence=self.sequence, width=self.width,
                    height=self.height, bytes=len(self.pixels),
                    render_cycles=self.render_cycles, clock_hz=self.clock_hz,
                    render_seconds=self.render_seconds, copy_seconds=self.copy_seconds,
                    capture_seconds=self.capture_seconds)


def validate_geometry(width, height, stride, pixel_format, span=None):
    if not (0 < width <= 2048 and 0 < height <= 2048) or width % 2:
        raise ValueError('invalid geometry: width must be even; each dimension must be 1..2048')
    if stride != width * 2 or pixel_format != 1:
        raise ValueError('only tightly packed little-endian RGB565 format 1 is supported')
    size = stride * height
    if span is not None and FRAME_OFFSET + size > span:
        raise ValueError('frame exceeds mapping span; use the generated hardware address map')
    return size


class MMIOMapping:
    """Single-owner MMIO through mandatory volatile/barrier native accessors."""
    def __init__(self, base, span=DEFAULT_SPAN, path='/dev/mem',
                 lock_path='/run/lock/de10-gpu-platform.lock'):
        if sys.platform != 'linux':
            raise RuntimeError('real MMIO backend requires Linux on the HPS')
        if not isinstance(base, int) or base < 0 or base > 0xffffffff or base % mmap.PAGESIZE:
            raise ValueError('base must be an explicit page-aligned 32-bit physical address')
        if span < FRAME_OFFSET + 4 or span % mmap.PAGESIZE or base + span > 0x100000000:
            raise ValueError('span must be a page multiple within the 32-bit physical address space')
        library_path = Path(__file__).resolve().with_name('libgpu_mmio.so')
        try:
            self._access = ctypes.CDLL(str(library_path))
        except OSError as error:
            raise RuntimeError('native MMIO helper is required; run sh software/build_mmio.sh '
                               'on the HPS: %s' % error) from error
        self._access.gpu_mmio_read32.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                               ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint32)]
        self._access.gpu_mmio_read32.restype = ctypes.c_int
        self._access.gpu_mmio_write32.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                                ctypes.c_size_t, ctypes.c_uint32]
        self._access.gpu_mmio_write32.restype = ctypes.c_int
        import fcntl
        self.span = span
        self._lock = None
        self._fd = None
        self._map = None
        try:
            self._lock = open(lock_path, 'a+b')
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd = os.open(path, os.O_RDWR | os.O_SYNC)
            self._map = mmap.mmap(self._fd, span, flags=mmap.MAP_SHARED,
                                  prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
            self._address = ctypes.addressof(ctypes.c_uint32.from_buffer(self._map))
        except BaseException:
            self.close()
            raise

    def _check(self, offset):
        if self._map is None:
            raise RuntimeError('MMIO mapping is closed')
        if offset < 0 or offset % 4 or offset + 4 > self.span:
            raise ValueError('MMIO access must be an aligned in-range 32-bit word')

    def read32(self, offset):
        self._check(offset)
        value = ctypes.c_uint32()
        error = self._access.gpu_mmio_read32(self._address, self.span, offset, ctypes.byref(value))
        if error:
            raise OSError(error, 'native MMIO read rejected')
        return value.value

    def write32(self, offset, value):
        self._check(offset)
        error = self._access.gpu_mmio_write32(self._address, self.span, offset, value)
        if error:
            raise OSError(error, 'native MMIO write rejected')

    def close(self):
        if self._map is not None:
            self._map.close()
            self._map = None
            self._address = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._lock is not None:
            self._lock.close()
            self._lock = None


class Device:
    def __init__(self, base=None, span=DEFAULT_SPAN, path='/dev/mem',
                 lock_path='/run/lock/de10-gpu-platform.lock', *, transport=None):
        # transport is an explicit test seam, not an automatic fallback.
        if transport is None and base is None:
            raise ValueError('an explicit verified physical --base is required')
        self.io = transport if transport is not None else MMIOMapping(base, span, path, lock_path)
        self.span = getattr(self.io, 'span', span)
        try:
            identity, abi = self.io.read32(0x00), self.io.read32(0x04)
            if identity != GPU_ID or abi != ABI_VERSION:
                raise RuntimeError('FPGA identity mismatch: ID=0x%08x ABI=%d (expected GPU1 ABI 1)' %
                                   (identity, abi))
            self.width, self.height = self.io.read32(0x10), self.io.read32(0x14)
            self.size = validate_geometry(self.width, self.height, self.io.read32(0x18),
                                          self.io.read32(0x1c), self.span)
        except BaseException:
            self.close()
            raise

    def capture_pattern(self, timeout=2.0):
        if timeout <= 0 or not timeout < float('inf'):
            raise ValueError('timeout must be finite and positive')
        started = time.monotonic()
        deadline = started + timeout
        status = self.io.read32(0x08)
        if status & ~3 or status == 3:
            raise RuntimeError('invalid FPGA status 0x%x' % status)
        if status == 0:
            self.io.write32(0x0c, 1)
        while True:
            status = self.io.read32(0x08)
            if status & ~3 or status == 3:
                raise RuntimeError('invalid FPGA status 0x%x' % status)
            if status & 2:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('FPGA frame deadline expired; status=0x%x' % status)
            time.sleep(min(0.001, max(0, deadline - time.monotonic())))
        # A completed frame stays locked until release. Copy into ordinary HPS RAM.
        sequence = self.io.read32(0x20)
        cycles = self.io.read32(0x24)
        clock = self.io.read32(0x28)
        copy_start = time.monotonic()
        try:
            pixels = bytearray(self.size)
            for offset in range(0, self.size, 4):
                struct.pack_into('<I', pixels, offset, self.io.read32(FRAME_OFFSET + offset))
            copied = bytes(pixels)
            if self.io.read32(0x20) != sequence or self.io.read32(0x08) != 2:
                raise RuntimeError('frame ownership violation during HPS copy')
            copy_seconds = time.monotonic() - copy_start
        finally:
            self.io.write32(0x0c, 2)
        return Frame(sequence, self.width, self.height, copied, cycles, clock,
                     copy_seconds, time.monotonic() - started,
                     'hardware' if isinstance(self.io, MMIOMapping) else 'test-transport')

    def close(self):
        self.io.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


class Snapshot:
    """Replay a captured raw framebuffer. This never exercises an FPGA."""
    def __init__(self, path, width=320, height=240):
        self.pixels = Path(path).read_bytes()
        self.width, self.height, self.sequence = width, height, 0
        Frame(0, width, height, self.pixels, source='offline-snapshot')

    def capture_pattern(self, timeout=2.0):
        self.sequence += 1
        return Frame(self.sequence, self.width, self.height, self.pixels,
                     source='offline-snapshot')

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


def check_pattern(frame):
    for y in range(frame.height):
        for x in range(frame.width):
            expected = ((x & 31) << 11) | ((y & 63) << 5) | ((x ^ y) & 31)
            actual = struct.unpack_from('<H', frame.pixels, (y * frame.width + x) * 2)[0]
            if actual != expected:
                raise ValueError('pattern mismatch at (%d,%d): got 0x%04x expected 0x%04x' %
                                 (x, y, actual, expected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--base', type=lambda value: int(value, 0), help='verified physical peripheral base')
    source.add_argument('--snapshot', type=Path, help='OFFLINE replay of raw RGB565 dump')
    parser.add_argument('--span', type=lambda value: int(value, 0), default=DEFAULT_SPAN)
    parser.add_argument('--width', type=int, default=320, help='offline snapshot width')
    parser.add_argument('--height', type=int, default=240, help='offline snapshot height')
    parser.add_argument('--timeout', type=float, default=2.0)
    parser.add_argument('--output', type=Path, default=Path('frame.rgb565'))
    parser.add_argument('--check-pattern', action='store_true')
    args = parser.parse_args()
    try:
        backend = (Snapshot(args.snapshot, args.width, args.height) if args.snapshot is not None
                   else Device(args.base, args.span))
        with backend:
            frame = backend.capture_pattern(args.timeout)
        if args.check_pattern:
            check_pattern(frame)
        args.output.write_bytes(frame.pixels)
        metrics = frame.metrics()
        metrics['pattern_checked'] = args.check_pattern
        args.output.with_suffix(args.output.suffix + '.json').write_text(
            json.dumps(metrics, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(metrics))
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        parser.exit(1, 'capture failed: %s\n' % error)


if __name__ == '__main__':
    main()
