# -*- coding: utf-8 -*-
"""Measure the live HPS server plus reaped native helpers; no GPU accesses."""
from __future__ import print_function
import argparse
import json
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from legacy_host import monotonic

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=float, default=10)
args = parser.parse_args()
if not 1 <= args.seconds <= 60:
    parser.error('--seconds must be 1..60')
with open('/root/de10_gpu_platform/software/spinal-server.pid') as source:
    pid = int(source.read())

def sample():
    with open('/proc/%d/stat' % pid) as source:
        fields = source.read().rsplit(')', 1)[1].split()
    # fields starts at original stat field3; include utime,stime,cutime,cstime.
    return fields[19], sum(int(value) for value in fields[11:15])

identity, before = sample()
started = monotonic()
time.sleep(args.seconds)
after_identity, after = sample()
elapsed = monotonic() - started
if identity != after_identity:
    raise RuntimeError('producer process changed during observation')
cpu_seconds = (after - before) / float(os.sysconf('SC_CLK_TCK'))
print(json.dumps(dict(source='live-hps-producer-cpu', pid=pid,
                      duration_seconds=elapsed, cpu_seconds=cpu_seconds,
                      percent_of_one_core=100 * cpu_seconds / elapsed,
                      scope='server plus reaped native children; excludes unrelated processes and system-wide IRQ work')))
