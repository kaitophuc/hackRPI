"""Exercise the generated 32-to-256-bit depth/DDR fabric without an HPS model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submodules', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--simulator', choices=['verilator', 'questa'], default='verilator')
    parser.add_argument('--questa-bin', type=Path)
    parser.add_argument('--wsl-distro', default='Ubuntu')
    args = parser.parse_args()
    directory, output = args.submodules.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources, texts = {}, {}
    for path in sorted(directory.iterdir()):
        if path.suffix in ('.v', '.sv'):
            text = path.read_text(errors='replace')
            texts[path] = text
            for name in re.findall(r'(?m)^\s*module\s+(\w+)', text):
                sources[name] = path
    top = 'spinal_system_mm_interconnect_0'
    fabric = sources[top]
    reachable, pending = set(), [fabric]
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        reachable.add(path)
        for token in set(re.findall(r'\b\w+\b', texts[path])) & sources.keys():
            if sources[token] not in reachable:
                pending.append(sources[token])
    header = texts[fabric].split('\n\t);', 1)[0]
    ports = re.findall(r'(input|output)\s+wire\s*(\[[^]]+\])?\s*(\w+)', header)
    declarations, connections = [], []
    for direction, width, name in ports:
        if 'reset_bridge' in name or name.endswith('_reset'):
            signal = 'reset'
        elif name.endswith('_clk'):
            signal = 'clk'
        else:
            signal = name.replace('spinal_gpu_0_fb_aux_read_', 'aux_').replace('hps_0_f2h_sdram0_data_', 'mem_')
            kind = 'reg' if direction == 'input' else 'wire'
            declarations.append('%s %s %s%s;' % (kind, width, signal, '=0' if kind == 'reg' else ''))
        connections.append('.%s(%s)' % (name, signal))
    test = '`timescale 1ns/1ps\nmodule tb_qsys_depth;\nreg clk=0, reset=1;always #10 clk=~clk;\n'
    test += '\n'.join(declarations) + '\n' + top + ' fabric(\n' + ',\n'.join(connections) + '\n);\n'
    test += Path(__file__).with_name('tb_qsys_depth_body.svh').read_text() + '\nendmodule\n'
    bench = output / 'tb_qsys_depth.sv'
    bench.write_text(test)
    if args.simulator == 'questa':
        if args.questa_bin is None:
            parser.error('--questa-bin is required for Questa')
        tools = args.questa_bin.resolve()
        library = output / 'work'
        with (output / 'compile.log').open('w') as log:
            subprocess.run([str(tools / 'vlib.exe'), str(library)], cwd=output, stdout=log, stderr=log, check=True)
            subprocess.run([str(tools / 'vlog.exe'), '-sv', '-work', str(library), str(bench)] +
                           [str(path) for path in sorted(reachable)], cwd=output, stdout=log, stderr=log, check=True)
        (output / 'run.do').write_text('onerror {quit -code 1}\nonbreak {quit -code 1}\nrun -all\nquit -code 0\n')
        with (output / 'simulation.log').open('w') as log:
            subprocess.run([str(tools / 'vsim.exe'), '-c', '-lib', str(library), 'tb_qsys_depth', '-do', 'do run.do'],
                           cwd=output, stdout=log, stderr=log, check=True)
        print((output / 'simulation.log').read_text())
        return
    files = [bench] + sorted(reachable)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    (output / 'simulation-source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
    build_dir = '/tmp/hackrpi-depth-fabric-' + key
    def linux_path(path):
        if os.name != 'nt':
            return str(path)
        if not re.fullmatch(r'[A-Za-z]:', path.drive):
            raise ValueError('WSL simulation requires a local drive path')
        return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]
    prefix = ['wsl', '-d', args.wsl_distro, '--'] if os.name == 'nt' else []
    with (output / 'compile.log').open('w') as log:
        subprocess.run(prefix + ['verilator', '--binary', '--timing', '--assert', '-Wno-fatal', '-j', '2',
                       '--top-module', 'tb_qsys_depth', '--Mdir', build_dir] + [linux_path(path) for path in files],
                       stdout=log, stderr=log, check=True)
    with (output / 'simulation.log').open('w') as log:
        subprocess.run(prefix + [build_dir + '/Vtb_qsys_depth'], stdout=log, stderr=log, check=True)
    print((output / 'simulation.log').read_text())


if __name__ == '__main__':
    main()
