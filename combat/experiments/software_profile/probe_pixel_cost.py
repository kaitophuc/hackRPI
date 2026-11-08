"""Diagnostic only: compare equal command counts with smaller triangle areas."""
from __future__ import print_function
import hashlib,json,os,shutil,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-pixel-cost'
if not os.path.isdir(probe):os.mkdir(probe)
paths=['combat/dist/libflighting_spinal_bridge.so','combat/native/spinal_pipeline.c','combat/native/spinal_color_cache.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes();source=open(paths[1]).read().replace('\r\n','\n')
def change(old,new):
    global source
    if source.count(old)!=1:raise RuntimeError('Unexpected diagnostic marker: '+old[:60])
    source=source.replace(old,new)
change('#include "spinal_bridge.c"','#include "/root/hackrpi/combat/native/spinal_bridge.c"\nunsigned flighting_probe_commands;')
change('unsigned char pixels[BYTES];','unsigned probe_commands;unsigned char pixels[BYTES];')
change('    f->count++;return 0;','''    if(getenv("SPINAL_PROBE_SMALL_AREA")&&strcmp(getenv("SPINAL_PROBE_SMALL_AREA"),"1")==0){
        unsigned p;for(p=0;p<d->count;p++){d->v[p].x=160+(d->v[p].x-160)*.25f;d->v[p].y=120+(d->v[p].y-120)*.25f;}
    }
    f->count++;return 0;''')
change('    configure();grRenderBuffer(number','    flighting_probe_commands=0;configure();grRenderBuffer(number')
change('    submitted=f->triangles;','    slot->probe_commands=flighting_probe_commands;submitted=f->triangles;')
change('\\"readback_overlap\\":true}','\\"probe_triangle_commands\\":%u,\\"readback_overlap\\":true}')
change('slot->previous_submit_ms);','slot->previous_submit_ms,slot->probe_commands);')
with open(probe+'/pipeline.c','w') as f:f.write(source)
colors=open(paths[2]).read().replace('\r\n','\n')
colors=colors.replace('extern int flighting_flat_colors;','extern int flighting_flat_colors;\nextern unsigned flighting_probe_commands;')
colors=colors.replace('    if(flighting_flat_colors){','    if(offset==0x100)flighting_probe_commands++;\n    if(flighting_flat_colors){')
with open(probe+'/colors.c','w') as f:f.write(colors)
build=open('combat/board/build_native.sh').read().replace('root=$(CDPATH= cd -- "$here/../.." && pwd)','root=/root/hackrpi')
build=build.replace('$root/combat/native/spinal_pipeline.c',probe+'/pipeline.c').replace('$root/combat/native/spinal_color_cache.c',probe+'/colors.c')
build=build.replace('$root/build/software-profile/cached-colors.o',probe+'/colors.o').replace('$root/combat/dist/libflighting_spinal_bridge.so.next',probe+'/libflighting_spinal_bridge.so')
build=build[:build.index('\nmv ')]+'\n'
process=subprocess.Popen(['sh','-s'],stdin=subprocess.PIPE);process.communicate(build.encode('ascii'))
if process.returncode:raise RuntimeError('Diagnostic build failed')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    for label,small in [('pixel-cost-before','0'),('pixel-cost-small','1'),('pixel-cost-after','0')]:
        subprocess.check_call(['python',folder+'/probe_setup_cost.py',probe+'/libflighting_spinal_bridge.so',label],
                              env=dict(os.environ,SPINAL_PROBE_SMALL_AREA=small,SPINAL_READBACK_BATCH='1'))
    results=[json.load(open(folder+'/'+label+'-setup-cost.json')) for label in ('pixel-cost-before','pixel-cost-small','pixel-cost-after')]
    summary=[]
    for rows in zip(*[r['scenes'] for r in results]):
        if len(set(r['scene'] for r in rows))!=1:raise RuntimeError('Scene mismatch')
        commands=[set(s['actual_triangle_commands'] for s in r['observations']) for r in rows]
        if any(len(c)!=1 for c in commands) or commands[0]!=commands[1] or commands[0]!=commands[2]:raise RuntimeError('Triangle command counts changed')
        if len(rows[0]['pixel_hashes'])!=1 or rows[0]['pixel_hashes']!=rows[2]['pixel_hashes']:raise RuntimeError('Original-area pixels did not restore exactly')
        summary.append(dict(scene=rows[0]['scene'],actual_commands=list(commands[0])[0],
                            command_ms=[r['median']['command_ms'] for r in rows],
                            gpu_busy_ms=[r['median']['gpu_busy_ms'] for r in rows]))
    with open(folder+'/pixel-cost-summary.json','w') as f:json.dump(dict(diagnostic_only=True,scenes=summary),f,indent=2)
    print(json.dumps(summary,indent=2))
finally:
    after=hashes();subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=after:raise RuntimeError('Production sources or binary changed')
print(json.dumps(dict(production_unchanged=True)))
