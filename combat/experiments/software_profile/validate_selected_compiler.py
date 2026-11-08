"""Validate the deployed compiler build against all selected pre-change pixels."""
from __future__ import print_function
import glob,hashlib,json,os,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';reference='/dev/shm/hackrpi-compiler-reference';library='combat/dist/libflighting_spinal_bridge.so'
manifest=json.load(open(folder+'/compiler-cross-reference.json'))
if not manifest.get('passed') or manifest.get('reference_scenes')!=22:raise RuntimeError('Cross-build reference is incomplete')
for name,digest in manifest['reference_hashes'].items():
    if hashlib.sha256(open(reference+'/'+name,'rb').read()).hexdigest()!=digest:raise RuntimeError('Pixel baseline changed: '+name)
before=hashlib.sha256(open(library,'rb').read()).hexdigest()
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         LD_LIBRARY_PATH='/root/hackrpi/combat/dist',SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',
         SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',FLIGHTING_CITY_XY_CACHE='1',SPINAL_READBACK_BATCH='1',
         FLIGHTING_VALIDATION_BASELINE_DIR=reference,FLIGHTING_VALIDATION_REQUIRE_BASELINE='1')
samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
if len(samples)!=14:raise RuntimeError('Expected fourteen saved scenes')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    with open(folder+'/compiler-deployed-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Compiler.exe']+samples,env=env,stdout=log,stderr=log)
finally:
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if hashlib.sha256(open(library,'rb').read()).hexdigest()!=before:raise RuntimeError('Deployed library changed')
with open(folder+'/compiler-deployed-validation.json','w') as f:json.dump(dict(passed=True,frames=288,reference_scenes=22,library_sha256=before),f,indent=2)
print(json.dumps(dict(passed=True,frames=288,reference_scenes=22,library_sha256=before)))
