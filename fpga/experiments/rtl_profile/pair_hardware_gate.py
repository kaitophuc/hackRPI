"""Snapshot the tested build, prepare the pair-read build, and audit its fit.

No JTAG, board access, constraint changes, or synthesis invocation.
"""
import argparse,hashlib,json,pathlib,re,shutil,time

ROOT=pathlib.Path(__file__).resolve().parents[3]
PROJECT=ROOT/'build/rtl-profile/quartus-project/hardware/spinal_standard'
BASE=ROOT/'build/rtl-profile/pipelined-build'
PAIR=ROOT/'build/rtl-profile/pair-rtl'
OUTPUT=PROJECT/'output_files'
NAME='Spinal_Standard_GPU'
CORES=[PROJECT/'rtl/SpinalStandardCore.v',PROJECT/'spinal_system/synthesis/submodules/rtl/SpinalStandardCore.v']
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def header(path):return re.search(r'(?ms)^module SpinalStandardCore \(.*?^\);',path.read_text()).group()
def pins(path):
    result={}
    for line in path.read_text().splitlines():
        fields=[s.strip() for s in line.split(':')]
        if len(fields)==7 and fields[2] in ('input','output','bidir'):result[fields[0]]=fields[1:]
    return result
def timing(path):
    return {name:dict(slack=float(slack),tns=float(tns)) for name,slack,tns in
            re.findall(r'Type\s*:\s*(.*?)\nSlack\s*:\s*([-\d.]+)\nTNS\s*:\s*([-\d.]+)',path.read_text())}
def unconstrained(path):
    pattern=r'^;\s*(Illegal Clocks|Unconstrained Clocks|Unconstrained Input Ports|Unconstrained Input Port Paths|Unconstrained Output Ports|Unconstrained Output Port Paths)\s*;\s*(\d+)\s*;\s*(\d+)\s*;'
    return {name:[int(a),int(b)] for name,a,b in re.findall(pattern,path.read_text(),re.M)}
def inputs():
    extensions={'.v','.sv','.vhd','.tcl','.sdc','.qsf','.qpf','.qip','.qsys','.bin','.mif','.hex'}
    excluded={'db','incremental_db','output_files'}
    return {p.relative_to(PROJECT).as_posix():digest(p) for p in PROJECT.rglob('*')
            if p.is_file() and p.suffix in extensions and not excluded.intersection(p.relative_to(PROJECT).parts) and p not in CORES}
def prepare():
    matrix=json.loads((ROOT/'build/rtl-profile/pair-matrix/results.json').read_text())
    if not matrix.get('complete') or not matrix.get('zero_additional_pixel_differences'):raise RuntimeError('Pixel matrix must pass first')
    candidate=digest(PAIR/'SpinalStandardCore.v')
    if len(matrix['cases'])!=14 or any(c['candidate']['rtl_sha256']!=candidate for c in matrix['cases']):raise RuntimeError('Matrix does not cover this core')
    log_data=(ROOT/'build/rtl-profile/pair-all-tests.log').read_bytes()
    log=log_data.decode('utf-16' if log_data.startswith(b'\xff\xfe') else 'utf-8-sig')
    if 'All tests passed.' not in log or 'Total number of tests run: 15' not in log:raise RuntimeError('Protocol suite must pass first')
    manifest=json.loads((pathlib.Path(__file__).parent/'candidate-manifest.json').read_text())
    for core in CORES:
        if digest(core)!=manifest['candidate_core_sha256']:raise RuntimeError('Unexpected previous build core')
        if header(core)!=header(PAIR/'SpinalStandardCore.v'):raise RuntimeError('Core external ports changed')
    roms=list(PAIR.glob('*.bin'))
    if len(roms)!=11:raise RuntimeError('Expected eleven generated ROM sidecars')
    for rom in roms:
        for core in CORES:
            if digest(core.parent/rom.name)!=digest(rom):raise RuntimeError('ROM content changed')
    if digest(OUTPUT/(NAME+'.sof'))!=manifest['candidate_sof_sha256']:raise RuntimeError('Unexpected previous build image')
    if BASE.exists():raise RuntimeError('Refuse to overwrite the saved tested build')
    BASE.mkdir(parents=True)
    shutil.copytree(OUTPUT,BASE/'output_files')
    record=dict(prepared_time=time.time(),previous_sof_sha256=manifest['candidate_sof_sha256'],
                core_sha256=candidate,unchanged_inputs=inputs(),
                pair_source_hashes={n:digest(ROOT/'build/rtl-profile/pair-src'/n) for n in
                    ('src/voodoo/framebuffer/FramebufferPlanePairReader.scala','src/voodoo/core/FramebufferMemSubsystem.scala','src/voodoo/pixel/FramebufferAccess.scala')})
    for core in CORES:shutil.copyfile(PAIR/'SpinalStandardCore.v',core)
    (BASE/'build-inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Prepared pair build; saved tested image and reports at '+str(BASE))
    print('Candidate core SHA256: '+candidate)
def verify():
    record=json.loads((BASE/'build-inputs.json').read_text())
    if inputs()!=record['unchanged_inputs']:raise RuntimeError('A board, DDR, constraint, ROM, or other HDL input changed')
    if any(digest(core)!=record['core_sha256'] for core in CORES):raise RuntimeError('Compiled source differs from tested core')
    image=OUTPUT/(NAME+'.sof')
    if image.stat().st_mtime<record['prepared_time']:raise RuntimeError('No new fitted image')
    if 'Fitter Status : Successful' not in (OUTPUT/(NAME+'.fit.summary')).read_text():raise RuntimeError('Fit failed')
    before=BASE/'output_files';before_pins=pins(before/(NAME+'.pin'));after_pins=pins(OUTPUT/(NAME+'.pin'))
    if len(before_pins)!=342 or before_pins!=after_pins:raise RuntimeError('Compiled pin assignments changed')
    if len([name for name in after_pins if name.startswith('HPS_DDR3_')])!=72:raise RuntimeError('HPS DDR pin coverage incomplete')
    old_timing=timing(before/(NAME+'.sta.summary'));new_timing=timing(OUTPUT/(NAME+'.sta.summary'))
    if not new_timing or old_timing.keys()!=new_timing.keys():raise RuntimeError('Constrained clock checks changed')
    if any(t['slack']<0 or t['tns']!=0 for t in new_timing.values()):raise RuntimeError('Timing failed')
    old_unconstrained=unconstrained(before/(NAME+'.sta.rpt'));new_unconstrained=unconstrained(OUTPUT/(NAME+'.sta.rpt'))
    if len(old_unconstrained)!=6 or old_unconstrained!=new_unconstrained:raise RuntimeError('Unconstrained path coverage changed')
    result=dict(timing_passed=True,timing_entries=new_timing,minimum_slack=min(t['slack'] for t in new_timing.values()),
                all_compiled_pin_assignments_identical=True,compiled_pin_assignment_count=len(after_pins),hps_ddr_pins_verified=True,
                unchanged_unconstrained_summary=new_unconstrained,unchanged_board_memory_and_constraint_inputs=len(record['unchanged_inputs']),
                sof_sha256=digest(image),core_sha256=record['core_sha256'],clock_mhz=50)
    destination=ROOT/'build/rtl-profile/pair-hardware-gate.json';destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('timing_entries','unchanged_unconstrained_summary')},indent=2))
p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','verify'));a=p.parse_args()
prepare() if a.command=='prepare' else verify()
