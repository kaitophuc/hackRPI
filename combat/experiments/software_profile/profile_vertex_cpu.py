"""Run the isolated vertex prototype's CPU-only checks while preserving services."""
from __future__ import print_function
import hashlib,json,os,re,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-vertex-candidate'
paths=['combat/dist/Flighting.Headless.exe','combat/dist/libflighting_spinal_bridge.so','combat/native/spinal_pipeline.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes()
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         LD_LIBRARY_PATH='/root/hackrpi/combat/dist',FLIGHTING_CITY_XY_CACHE='1',FLIGHTING_PACKED_REUSE='1',FLIGHTING_DIRECT_VERTEX_BUFFER='1')
def run(label,exe,args):
    with open(folder+'/'+label+'.log','w') as log:
        subprocess.check_call(['nice','-n','10','runtime/usr/bin/mono-sgen',exe]+args,env=env,stdout=log,stderr=log)
    return open(folder+'/'+label+'.log').read()
run('vertex-buffer-arm-checks',probe+'/VertexBufferChecks.exe',[])
reference=run('vertex-reference-arm',probe+'/VertexProfile.exe',['reference','600'])
old=[line for line in open(folder+'/xy-reference-after.log') if line.startswith('REFERENCE ')]
new=[line+'\n' for line in reference.splitlines() if line.startswith('REFERENCE ')]
if len(old)!=7 or old!=new:raise RuntimeError('Original geometry/CPU reference changed')
results=dict(reference_checkpoints=7,geometry_and_cpu_images_identical=True,production_unchanged=False,timings={})
for label,exe in [('vertex-geometry-before',folder+'/BeforeVertexProfile.exe'),('vertex-geometry-direct',probe+'/VertexProfile.exe'),('vertex-geometry-after',folder+'/BeforeVertexProfile.exe')]:
    text=run(label,exe,['geometry','300'])
    values={key:float(value) for key,value in re.findall(r'(median_ms|p95_ms|cpu_ms|retained_bytes)=([0-9.]+)',text)}
    results['timings'][label]=values;print(json.dumps(dict(label=label,measurements=values)))
after=hashes()
if before!=after:raise RuntimeError('Production sources or binaries changed')
results['production_unchanged']=True
with open(folder+'/vertex-cpu-results.json','w') as f:json.dump(results,f,indent=2)
print(json.dumps(results,indent=2))
