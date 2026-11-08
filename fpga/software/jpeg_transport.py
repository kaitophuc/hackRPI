# -*- coding: utf-8 -*-
"""Optional native RGB565 -> JPEG adapter, compatible with Python 2.7/3.

This encoder only compresses an immutable CPU snapshot. It never renders a scene
and never touches FPGA registers. A helper deadline bounds a failed encoder.
"""
import json
import math
import subprocess
import threading
import time

try:
    monotonic = time.monotonic
except AttributeError:
    from legacy_host import monotonic


class NativeJPEGEncoder(object):
    def __init__(self, helper, quality=75, timeout=2.0):
        if not 1 <= quality <= 100:
            raise ValueError('JPEG quality must be 1..100')
        self.helper, self.quality, self.timeout = helper, quality, timeout

    def encode(self, frame):
        started = monotonic()
        command = [self.helper, '--stdin', '--stdout', '--width', str(frame.width),
                   '--height', str(frame.height), '--quality', str(self.quality)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        done, output = threading.Event(), []

        def collect():
            try:
                output.append(process.communicate(frame.pixels))
            except Exception as exc:
                output.append(exc)
            finally:
                done.set()
        reader = threading.Thread(target=collect)
        reader.daemon = True
        reader.start()
        if not done.wait(self.timeout):
            process.kill()
            reader.join(2.0)
            raise RuntimeError('JPEG helper deadline expired')
        reader.join()
        if isinstance(output[0], Exception):
            raise output[0]
        jpeg, errors = output[0]
        if process.returncode:
            raise RuntimeError('JPEG helper failed (%d): %s' %
                               (process.returncode, errors.decode('utf-8', 'replace')[:2048]))
        try:
            metadata = json.loads(errors.decode('utf-8').strip())
            if metadata['source'] != 'native-rgb565-jpeg-encoder' or metadata['frames'] != 1:
                raise ValueError('wrong encoder provenance')
            if metadata['width'] != frame.width or metadata['height'] != frame.height or metadata['quality'] != self.quality:
                raise ValueError('encoder geometry/quality mismatch')
            if len(jpeg) < 4 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                raise ValueError('invalid JPEG markers')
            if len(jpeg) > frame.width * frame.height * 6 + 65536 or metadata['bytes'] != len(jpeg):
                raise ValueError('invalid JPEG size')
            for field in ('mean_encode_ms', 'cpu_ms', 'rgb_conversion_ms', 'jpeg_ms'):
                value = float(metadata[field])
                if value < 0 or math.isnan(value) or math.isinf(value):
                    raise ValueError('invalid JPEG timing')
            metadata['helper_wall_ms'] = (monotonic() - started) * 1000
            return jpeg, metadata
        except (ValueError, TypeError, KeyError) as exc:
            raise RuntimeError('invalid JPEG helper result: %s' % exc)
