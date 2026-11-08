# -*- coding: utf-8 -*-
"""Read-only, boot-specific evidence for the Standard GPU DDR exclusion.

Python 2.7/3 compatible. Exit zero establishes only the checked runtime
exclusions, not a permanent DT reservation or proof against arbitrary firmware.
No bridge configuration, raw-memory write, or renderer command is performed.
Run while other GPU producers are stopped; later processes can invalidate it.
The native MMIO library must already have been built with build_mmio.sh.
"""
from __future__ import print_function
import argparse
import ctypes
import errno
import glob
import gzip
import json
import os
import re
import sys
import time

POOL_START, POOL_END = 0x3f400000, 0x40000000
HPS_PORT_REGISTER = 0xffc25080
EXPECTED_PORT_MASK = 0x1ff  # generated hps.pre.xml F2SDRAM_RESET_PORT_USED
DT_ROOT = '/sys/firmware/devicetree/base'


def read(path, binary=False):
    with open(path, 'rb' if binary else 'r') as source:
        return source.read()


def overlaps(start, end):
    return start < POOL_END and end > POOL_START


def parse_ranges(text):
    """Linux iomem/memblock ranges are inclusive; return half-open ranges."""
    result = []
    for line in text.splitlines():
        match = re.search(r'(?:0x)?([0-9a-fA-F]+)\s*(?:\.\.|-)\s*(?:0x)?([0-9a-fA-F]+)', line)
        if match:
            result.append((int(match.group(1), 16), int(match.group(2), 16) + 1))
    return result


def mmio_port_state():
    """Read one aligned 32-bit HPS register through the native accessor."""
    library = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'libgpu_mmio.so'))
    native = ctypes.CDLL(library)
    native.gpu_mmio_read32.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint32)]
    native.gpu_mmio_read32.restype = ctypes.c_int
    libc = ctypes.CDLL(None, use_errno=True)
    # mmap64 handles ARM32's signed/large physical offsets explicitly.
    libc.mmap64.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
    libc.mmap64.restype = ctypes.c_void_p
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.munmap.restype = ctypes.c_int
    page = os.sysconf('SC_PAGESIZE')
    base = HPS_PORT_REGISTER & ~(page - 1)
    descriptor = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    mapping = None
    try:
        mapping = libc.mmap64(None, page, 1, 1, descriptor, base)  # READ, SHARED
        if mapping == ctypes.c_void_p(-1).value:
            mapping = None
            raise OSError(ctypes.get_errno(), 'read-only HPS mmap failed')
        value = ctypes.c_uint32()
        status = native.gpu_mmio_read32(mapping, page, HPS_PORT_REGISTER - base,
                                        ctypes.byref(value))
        if status:
            raise OSError(status, 'native HPS register read failed')
        return value.value
    finally:
        if mapping is not None:
            libc.munmap(mapping, page)
        os.close(descriptor)


def audit():
    result = dict(source='live-linux-ddr-audit', timestamp=time.time(),
                  pool_start=POOL_START, pool_end_exclusive=POOL_END,
                  errors=[], evidence={}, checked_runtime_exclusion=False,
                  persistent_reservation_established=False)
    errors, evidence = result['errors'], result['evidence']
    for name, path in [('iomem', '/proc/iomem'),
                       ('memblock_memory', '/sys/kernel/debug/memblock/memory'),
                       ('memblock_reserved', '/sys/kernel/debug/memblock/reserved')]:
        try:
            contents = read(path)
            ranges = parse_ranges(contents)
            evidence[name] = contents
            if not ranges:
                errors.append(name + ': no readable ranges')
            if any(overlaps(start, end) for start, end in ranges):
                errors.append(name + ': overlaps GPU pool')
        except (IOError, OSError) as error:
            errors.append(name + ': ' + str(error))
    try:
        with gzip.open('/proc/config.gz', 'rb') as source:
            config = source.read().decode('ascii')
        evidence['kernel_memory_config'] = [line for line in config.splitlines()
            if any(key in line for key in ('CONFIG_HIGHMEM', 'CONFIG_VMSPLIT', 'CONFIG_CMA'))]
        if '# CONFIG_HIGHMEM is not set' not in config:
            errors.append('requires re-audit: expected HIGHMEM disabled kernel')
    except (IOError, OSError) as error:
        errors.append('kernel config: ' + str(error))
    try:
        evidence['modules'] = read('/proc/modules')
        if evidence['modules'].strip():
            errors.append('loaded modules require review for independent physical-memory ownership')
        evidence['cmdline'] = read('/proc/cmdline').strip()
        evidence['dt_memory_reg_hex'] = ''.join('%02x' % value for value in bytearray(read(DT_ROOT + '/memory/reg', True)))
        if evidence['dt_memory_reg_hex'] != '0000000040000000':
            errors.append('unexpected DT DDR geometry: expected base0 size1GiB')
    except (IOError, OSError) as error:
        errors.append('kernel/DT evidence: ' + str(error))
    evidence['dt_memory_owners'] = []
    if not os.path.isdir(DT_ROOT):
        errors.append('live device tree unavailable')
    def tree_error(error):
        errors.append('device tree traversal: ' + str(error))
    for directory, subdirectories, files in os.walk(DT_ROOT, onerror=tree_error):
        if 'memory-region' in files or os.path.basename(directory).split('@')[0] == 'reserved-memory':
            evidence['dt_memory_owners'].append(directory)
    if evidence['dt_memory_owners']:
        errors.append('DT memory-region/reserved-memory owners require range review')
    evidence['physical_mappings'] = []
    for path in glob.glob('/proc/[0-9]*/maps'):
        try:
            lines = read(path).splitlines()
        except (IOError, OSError) as error:
            if error.errno != errno.ENOENT:  # Process exit is normal; unreadable owner is not.
                errors.append(path + ': ' + str(error))
            continue
        for line in lines:
            fields = line.split(None, 5)
            if len(fields) < 6:
                continue
            device = fields[5]
            if device.startswith('/dev/mem'):
                begin, end = [int(value, 16) for value in fields[0].split('-')]
                offset = int(fields[2], 16)
                evidence['physical_mappings'].append(dict(process=path, mapping=line))
                if overlaps(offset, offset + end - begin):
                    errors.append(path + ': active /dev/mem mapping overlaps pool')
            elif device.startswith(('/dev/uio', '/dev/udmabuf', '/dev/dma_heap')):
                evidence['physical_mappings'].append(dict(process=path, mapping=line))
                errors.append(path + ': DMA/UIO mapping requires physical-range review')
    try:
        value = mmio_port_state()
        evidence['sdr_fpgaportrst'] = value
        evidence['generated_required_port_mask'] = EXPECTED_PORT_MASK
        evidence['required_ports_out_of_reset'] = (value & EXPECTED_PORT_MASK) == EXPECTED_PORT_MASK
    except (OSError, AttributeError) as error:
        errors.append('HPS read-only register evidence: ' + str(error))
    result['checked_runtime_exclusion'] = not errors
    result['limitations'] = ('Boot-specific Linux allocator/reservation and mapped-owner exclusion only; '
                            'does not reserve DDR, prevent future raw access, or establish external firmware ownership.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='also save JSON inside /root/de10_gpu_platform')
    args = parser.parse_args()
    if args.output:
        destination = os.path.realpath(args.output)
        if not destination.startswith('/root/de10_gpu_platform/'):
            parser.error('--output must stay inside /root/de10_gpu_platform')
    result = audit()
    encoded = json.dumps(result, sort_keys=True, indent=2)
    if args.output:
        with open(destination, 'w') as output:
            output.write(encoded + '\n')
    print(encoded)
    return 0 if result['checked_runtime_exclusion'] else 1


if __name__ == '__main__':
    sys.exit(main())
