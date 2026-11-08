# -*- coding: utf-8 -*-
"""Python 2.7 compatible adapter for the native HPS capture helper.

The native program owns MMIO and releases the frame before writing stdout.
This module never renders pixels or silently substitutes an offline source.
"""
from __future__ import print_function
import collections
import ctypes
import json
import math
import os
import struct
import subprocess
import threading
import time

try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)


def _clock():
    if hasattr(time, 'monotonic'):
        return time.monotonic
    # CLOCK_MONOTONIC is 1 on the target Linux ABI. Python 2 lacks time.monotonic.
    class Timespec(ctypes.Structure):
        _fields_ = [('tv_sec', ctypes.c_long), ('tv_nsec', ctypes.c_long)]
    library = ctypes.CDLL('librt.so.1', use_errno=True)
    clock_gettime = library.clock_gettime
    clock_gettime.argtypes = [ctypes.c_int, ctypes.POINTER(Timespec)]
    clock_gettime.restype = ctypes.c_int

    def read_clock():
        value = Timespec()
        if clock_gettime(1, ctypes.byref(value)):
            raise OSError(ctypes.get_errno(), 'clock_gettime(CLOCK_MONOTONIC) failed')
        return value.tv_sec + value.tv_nsec / 1e9
    return read_clock


monotonic = _clock()
_Frame = collections.namedtuple('_Frame', 'sequence width height pixels render_cycles clock_hz copy_seconds capture_seconds source')


class Frame(_Frame):
    __slots__ = ()

    def __new__(cls, sequence, width, height, pixels, render_cycles=0, clock_hz=0,
                copy_seconds=0.0, capture_seconds=0.0, source='hardware'):
        if not 0 < width <= 2048 or width % 2 or not 0 < height <= 2048:
            raise ValueError('invalid RGB565 geometry')
        if not isinstance(pixels, bytes) or len(pixels) != width * height * 2:
            raise ValueError('pixels must be exact immutable RGB565 bytes')
        return _Frame.__new__(cls, sequence, width, height, pixels, render_cycles,
                              clock_hz, copy_seconds, capture_seconds, source)

    @property
    def render_seconds(self):
        return self.render_cycles / float(self.clock_hz) if self.clock_hz else 0.0

    def to_wire(self):
        return struct.pack('<4sIIIII', b'GPU1', self.sequence & 0xffffffff,
                           self.width, self.height, 1, len(self.pixels)) + self.pixels

    def metrics(self):
        result = self._asdict()
        result.pop('pixels')
        result.update(bytes=len(self.pixels), render_seconds=self.render_seconds)
        return result


class Device(object):
    """Each capture invokes the bounded native MMIO program on the existing SD."""
    def __init__(self, base, span=0x27000, helper=None):
        if base is None or base < 0 or base > 0xffffffff or base % 4096:
            raise ValueError('an explicit page-aligned 32-bit physical base is required')
        if span < 0x2000 or span % 4096 or base + span > 0x100000000:
            raise ValueError('invalid mapping span')
        self.base, self.span = base, span
        self.helper = helper or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capture')
        self.last_metadata = {}

    def _command(self, timeout):
        return [self.helper, '--base', '0x%x' % self.base, '--span', '0x%x' % self.span,
                '--stdout', '--timeout', str(timeout)]

    def _process_timeout(self, timeout):
        return timeout + 1.0

    def _validate_metadata(self, metadata):
        pass

    def capture_pattern(self, timeout=2.0):
        if timeout <= 0 or math.isinf(timeout) or math.isnan(timeout):
            raise ValueError('timeout must be finite and positive')
        started = monotonic()
        process = subprocess.Popen(self._command(timeout),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        done = threading.Event()
        result = []

        def collect():
            try:
                result.append(process.communicate())
            except Exception as exc:
                result.append(exc)
            finally:
                done.set()

        reader = threading.Thread(target=collect)
        reader.daemon = True
        reader.start()
        if not done.wait(self._process_timeout(timeout)):
            process.kill()
            reader.join(2.0)
            raise RuntimeError('native capture deadline expired')
        reader.join()
        if isinstance(result[0], Exception):
            raise result[0]
        pixels, stderr = result[0]
        if process.returncode:
            raise RuntimeError('native capture failed (%d): %s' %
                               (process.returncode, stderr.decode('utf-8', 'replace')[:2048]))
        try:
            metadata = json.loads(stderr.decode('utf-8').strip())
            width, height = metadata['width'], metadata['height']
            for field in ('sequence', 'width', 'height', 'bytes', 'render_cycles', 'clock_hz'):
                value = metadata[field]
                if isinstance(value, bool) or not isinstance(value, INTEGER_TYPES) or not 0 <= value <= 0xffffffff:
                    raise ValueError('invalid native integer %s' % field)
            if not metadata['clock_hz']:
                raise ValueError('native clock must be positive')
            if metadata['source'] != 'hardware' or metadata['bytes'] != len(pixels):
                raise ValueError('native source or byte count mismatch')
            if width * height * 2 + 0x1000 > self.span:
                raise ValueError('frame exceeds configured mapping span')
            for field in ('copy_seconds', 'capture_seconds'):
                value = float(metadata[field])
                if value < 0 or math.isnan(value) or math.isinf(value):
                    raise ValueError('invalid native timing')
            self._validate_metadata(metadata)
            frame = Frame(metadata['sequence'], width, height, pixels,
                         metadata['render_cycles'], metadata['clock_hz'],
                         float(metadata['copy_seconds']), monotonic() - started, source='hardware')
            self.last_metadata = metadata
            return frame
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError('invalid native capture result: %s' % exc)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


class NativeRendererAdapter(Device):
    """Explicit opt-in for the GPU2 native renderer. No pattern fallback.

    Selecting this adapter is not evidence that a 3D bitstream passed hardware
    tests. The helper must validate GPU2 and ownership before it emits a frame.
    """
    available_scenes = ('triangle', 'depth', 'cube', 'textured-cube')
    note = 'Native SpinalVoodoo producer selected; CPU setup and FPGA rasterization, depth and texture work'

    def __init__(self, base, sidecar_base, helper, scene='triangle', angle=0.0,
                 angular_speed=30.0, depth_order='far-first', process_timeout=15.0):
        Device.__init__(self, base, span=0x1000000, helper=helper)
        if sidecar_base is None or sidecar_base < 0 or sidecar_base > 0xffffffff or sidecar_base % 4096:
            raise ValueError('an explicit page-aligned GPU2 sidecar base is required')
        if depth_order not in ('far-first', 'near-first'):
            raise ValueError('invalid depth order')
        if any(math.isnan(value) or math.isinf(value) for value in (angle, angular_speed, process_timeout)) or process_timeout <= 0:
            raise ValueError('renderer controls and deadline must be finite')
        self.sidecar_base, self.depth_order = sidecar_base, depth_order
        self.scene, self.angle, self.angular_speed = scene, angle % 360, angular_speed
        self.rotation_paused, self.rotation_lock = False, threading.Lock()
        self._angle_clock = monotonic()
        self.process_timeout = process_timeout
        self.set_scene(scene)

    def _update_angle(self):
        now = monotonic()
        if not self.rotation_paused:
            self.angle = (self.angle + (now - self._angle_clock) * self.angular_speed) % 360
        self._angle_clock = now

    def set_scene(self, scene):
        if scene not in self.available_scenes:
            raise ValueError('scene is not supported by the native renderer')
        with self.rotation_lock:
            self.scene = scene

    def set_rotation_paused(self, paused):
        with self.rotation_lock:
            self._update_angle()
            self.rotation_paused = bool(paused)

    def _command(self, timeout):
        with self.rotation_lock:
            self._update_angle()
            self._pending_scene, self._pending_angle = self.scene, self.angle
            return [self.helper, '--base', '0x%x' % self.base,
                    '--sidecar-base', '0x%x' % self.sidecar_base,
                    '--scene', self.scene, '--angle', '%.6f' % self.angle,
                    '--depth-order', self.depth_order, '--stdout', '--timeout', str(timeout)]

    def _process_timeout(self, timeout):
        # Native startup/Glide initialization is outside its fence poll timeout.
        return max(self.process_timeout, timeout + 1.0)

    def _validate_metadata(self, metadata):
        if metadata['width'] != 320 or metadata['height'] != 240:
            raise ValueError('GPU2 producer must return its configured 320x240 snapshot')
        if metadata.get('renderer') != 'SpinalVoodoo' or metadata.get('scene') != self._pending_scene:
            raise ValueError('native renderer/scene mismatch')
        angle = float(metadata.get('angle', float('nan')))
        if math.isnan(angle) or math.isinf(angle) or abs(angle - self._pending_angle) > .001:
            raise ValueError('native renderer angle mismatch')
        if metadata.get('depth_order') != self.depth_order:
            raise ValueError('native renderer depth order mismatch')
        cycles = metadata.get('pipeline_busy_cycles')
        if isinstance(cycles, bool) or not isinstance(cycles, INTEGER_TYPES) or not 0 <= cycles <= 0xffffffff:
            raise ValueError('invalid pipeline occupancy counter')
        if metadata.get('render_timing_semantics') != 'begin-to-fence including CPU submission gaps':
            raise ValueError('unknown renderer frame timing semantics')
        initialization = float(metadata.get('initialization_seconds', float('nan')))
        if initialization < 0 or math.isnan(initialization) or math.isinf(initialization):
            raise ValueError('invalid native initialization timing')


class Snapshot(object):
    """Explicit offline replay; never opens MMIO or invokes the helper."""
    def __init__(self, path, width=320, height=240):
        with open(path, 'rb') as source:
            self.pixels = source.read()
        self.width, self.height, self.sequence = width, height, 0
        Frame(0, width, height, self.pixels, source='offline-snapshot')

    def capture_pattern(self, timeout=2.0):
        self.sequence += 1
        return Frame(self.sequence, self.width, self.height, self.pixels, source='offline-snapshot')

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
