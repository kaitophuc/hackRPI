# -*- coding: utf-8 -*-
"""Read-only check of the diagnostic 64x64 RGB565 checker in audited GPU DDR."""
from __future__ import print_function
import fcntl
import hashlib
import json
import struct
import sys
import audit_ddr

with open('/run/lock/de10-gpu-platform.lock', 'a+') as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    words = []
    for offset in range(0, 8192, 4):
        audit_ddr.HPS_PORT_REGISTER = 0x3f800000 + offset
        words.append(struct.pack('<I', audit_ddr.mmio_port_state()))
    actual = b''.join(words)
expected = b''.join(struct.pack('<H', 0xffff if ((x // 8) ^ (y // 8)) & 1 else 0x001f)
                    for y in range(64) for x in range(64))
with open('/root/de10_gpu_platform/texture-ddr.bin', 'wb') as output:
    output.write(actual)
pixels = struct.unpack('<4096H', actual)
result = dict(source='hardware-reserved-ddr-read-only', bytes=len(actual),
              sha256=hashlib.sha256(actual).hexdigest(),
              expected_sha256=hashlib.sha256(expected).hexdigest(),
              mismatched_bytes=sum(a != b for a, b in zip(bytearray(actual), bytearray(expected))),
              color_counts=dict((hex(color), pixels.count(color)) for color in set(pixels)),
              passed=actual == expected)
print(json.dumps(result, sort_keys=True))
sys.exit(0 if result['passed'] else 1)
