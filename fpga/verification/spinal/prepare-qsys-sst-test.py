"""Build an offline harness from the actual generated AXI fabric and SST frontend."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
out = root / 'build/qsys-sst-test'
out.mkdir(parents=True, exist_ok=True)
core = (root / 'hardware/spinal_standard/rtl/SpinalStandardCore.v').read_text()
frontend = re.search(r'(?ms)^module H2fLwToBmbBridge\s*\(.*?^endmodule', core).group()
(out / 'frontend.v').write_text(frontend)
fabric = root / 'hardware/spinal_standard/spinal_system/synthesis/submodules/spinal_system_mm_interconnect_1.v'
ports = re.findall(r'(input|output)\s+wire\s*(\[[^]]+\])?\s*(\w+)', fabric.read_text().split('\n\t);', 1)[0])
decl, conns = [], []
for direction, width, name in ports:
    signal = name.removeprefix('hps_0_h2f_axi_master_').removeprefix('spinal_gpu_0_sst_')
    if name == 'clk_0_clk_clk': signal = 'clk'
    elif name.endswith('reset_reset_bridge_in_reset_reset'): signal = 'reset'
    if signal not in ('clk', 'reset'):
        kind = 'reg' if direction == 'input' and name.startswith('hps_0_') else 'wire'
        decl.append(f'{kind} {width} {signal};')
    conns.append(f'.{name}({signal})')
body = (Path(__file__).parent / 'tb_qsys_sst_body.svh').read_text()
text = '`timescale 1ns/1ps\nmodule tb_qsys_sst;\nreg clk=0, reset=1;\nalways #10 clk=~clk;\n'
text += '\n'.join(decl) + '\nspinal_system_mm_interconnect_1 fabric(\n' + ',\n'.join(conns) + '\n);\n' + body + '\nendmodule\n'
(out / 'tb_qsys_sst.sv').write_text(text)
print(out)
