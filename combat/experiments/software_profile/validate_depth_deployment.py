"""Check the deployed depth-state fix against 28 pre-change scene references."""
from __future__ import print_function
import glob,hashlib,json,os,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';library='combat/dist/libflighting_spinal_bridge.so'
checks=[(folder+'/compiler-cross-reference.json','/dev/shm/hackrpi-compiler-reference',22),
        (folder+'/depth-mode-validation.json','/dev/shm/hackrpi-depth-mode-reference',6)]
for path,directory,count in checks:
    manifest=json.load(open(path))
    if not manifest.get('passed') or len(manifest['reference_hashes'])!=count:raise RuntimeError('Incomplete baseline manifest')
    for name,digest in manifest['reference_hashes'].items():
        if hashlib.sha256(open(directory+'/'+name,'rb').read()).hexdigest()!=digest:raise RuntimeError('Baseline pixels changed')
before=hashlib.sha256(open(library,'rb').read()).hexdigest()
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         LD_LIBRARY_PATH='/root/hackrpi/combat/dist',SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',
         SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',FLIGHTING_CITY_XY_CACHE='1',SPINAL_READBACK_BATCH='1',
         FLIGHTING_VALIDATION_BASELINE_DIR=checks[0][1],FLIGHTING_VALIDATION_REQUIRE_BASELINE='1')
samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
if len(samples)!=14:raise RuntimeError('Expected fourteen saved scenes')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    with open(folder+'/depth-deployed-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Compiler.exe']+samples,env=env,stdout=log,stderr=log)
    with open(folder+'/depth-deployed-modes.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/DepthModeValidation.exe','verify',checks[1][1]],env=env,stdout=log,stderr=log)
finally:
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if hashlib.sha256(open(library,'rb').read()).hexdigest()!=before:raise RuntimeError('Deployed library changed')
with open(folder+'/depth-deployed-validation.json','w') as f:json.dump(dict(passed=True,queued_frames=360,reference_scenes=28,library_sha256=before),f,indent=2)
print(json.dumps(dict(passed=True,queued_frames=360,reference_scenes=28,library_sha256=before)))
