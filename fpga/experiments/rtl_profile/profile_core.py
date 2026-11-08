"""Profile the accepted full GPU RTL using a deterministic Avalon RAM model.

This is a diagnostic small scene, not measured board/displayed FPS. The
framebuffer and stride stay 320x240. Candidate pixels include both color
buffers and depth so a faster result cannot hide writes to the wrong buffer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PORTS = ('FbWrite', 'FbColorWrite', 'FbAuxWrite', 'FbColorRead', 'FbAuxRead', 'Tex')


def generate(rtl):
    source = rtl.read_text()
    header = re.search(r'(?ms)^module SpinalStandardCore \(.*?^\);', source).group()
    ports = re.findall(r'\b(input|output)\s+wire\s*(\[[^\]]+\])?\s*(\w+)', header)
    declarations, connections = [], []
    for direction, width, name in ports:
        if name in ('clk', 'reset'):
            signal = name
        elif name == 'io_hdmi_clock':
            signal = 'clk'
        elif name == 'io_hdmi_reset':
            signal = 'reset'
        else:
            signal = name
            kind = 'reg' if direction == 'input' and not name.startswith('io_mem') else 'wire'
            declarations.append('%s %s %s%s;' % (kind, width, name, '=0' if kind == 'reg' else ''))
        connections.append('.%s(%s)' % (name, signal))
    text = '`timescale 1ns/1ps\nmodule tb_core_profile;\nreg clk=0, reset=1; always #10 clk=~clk;\n'
    text += '\n'.join(declarations) + '\nSpinalStandardCore dut(\n' + ',\n'.join(connections) + '\n);\n'
    for port in PORTS:
        prefix = 'io_mem' + port
        text += ('profile_memory_port ram%s(.clk(clk), .reset(reset), .latency(memory_latency), .stall_period(stall_period),\n' % port)
        text += ',\n'.join('.%s(%s_%s)' % (field, prefix, name) for field, name in (
            ('read', 'read'), ('write', 'write'), ('waitn', 'waitRequestn'), ('address', 'address'),
            ('burst', 'burstCount'), ('mask', 'byteEnable'), ('data', 'writeData'),
            ('valid', 'readDataValid'), ('q', 'readData')))
        text += ');\n'
    text += (HERE / 'tb_core_profile.svh').read_text() + '\nendmodule\n'
    text += (HERE / 'profile_memory_port.sv').read_text()
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', type=Path, default=ROOT / 'fpga/hardware/spinal_standard/rtl/SpinalStandardCore.v')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--latency', type=int, default=16)
    parser.add_argument('--stall-period', type=int, default=0)
    parser.add_argument('--mode', choices=('flat', 'depth', 'textured', 'blend'), default='depth')
    parser.add_argument('--width', type=int, default=64)
    parser.add_argument('--height', type=int, default=32)
    parser.add_argument('--pairs', type=int, default=2)
    parser.add_argument('--pattern', choices=('same', 'mixed', 'buffers'), default='same')
    args = parser.parse_args()
    if not 1 <= args.latency <= 256 or not 0 <= args.stall_period <= 256:
        parser.error('Memory model settings out of range')
    if not 1 <= args.width <= 320 or not 1 <= args.height <= 240 or not 1 <= args.pairs <= 32:
        parser.error('Scene settings out of range')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rtl = args.rtl.resolve()
    testbench = output / 'tb_core_profile.sv'
    testbench.write_text(generate(rtl))
    for path in rtl.parent.glob('*.bin'):
        shutil.copyfile(path, output / path.name)
    simulation = output / 'profile.vvp'
    with (output / 'compile.log').open('w') as log:
        subprocess.run(['iverilog', '-g2012', '-s', 'tb_core_profile', '-o', str(simulation),
                        str(rtl), str(testbench)], cwd=output, stdout=log, stderr=log, check=True)
    command = ['vvp', str(simulation), '+LATENCY=' + str(args.latency), '+STALL=' + str(args.stall_period),
               '+MODE=' + str(('flat', 'depth', 'textured', 'blend').index(args.mode)),
               '+WIDTH=' + str(args.width), '+HEIGHT=' + str(args.height), '+PAIRS=' + str(args.pairs),
               '+PATTERN=' + str(('same', 'mixed', 'buffers').index(args.pattern))]
    with (output / 'simulation.log').open('w') as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=log, check=True)
    lines = (output / 'simulation.log').read_text().splitlines()
    record = json.loads(next(line[len('PROFILE '):] for line in lines if line.startswith('PROFILE ')))
    record.update(json.loads(next(line[len('MEMORY '):] for line in lines if line.startswith('MEMORY '))))
    record.update(mode=args.mode, memory_latency=args.latency, stall_period=args.stall_period,
                  scene_rectangle=[args.width, args.height], pairs=args.pairs, pattern=args.pattern,
                  framebuffer=[320, 240], diagnostic_not_board_fps=True,
                  rtl_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest(),
                  harness_sha256=hashlib.sha256(generate(rtl).encode()).hexdigest(),
                  pixel_sha256=hashlib.sha256((output / 'pixels.bin').read_bytes()).hexdigest())
    (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
