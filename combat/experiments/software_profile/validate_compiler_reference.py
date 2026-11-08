"""Compare all 22 scene baselines across selected and isolated compiler builds."""
from __future__ import print_function
import glob,hashlib,json,os,shutil,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-compiler-o3';reference='/dev/shm/hackrpi-compiler-reference';baseline='/dev/shm/hackrpi-compiler-baseline'
if not os.path.isdir(reference):os.mkdir(reference)
if not os.path.isdir(baseline):os.mkdir(baseline)
paths=['combat/dist/libflighting_spinal_bridge.so','combat/dist/Flighting.Headless.exe',
       'combat/native/spinal_pipeline.c','combat/native/spinal_color_cache.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes()
if before['combat/native/spinal_pipeline.c']!='af6cc7865a927cef236a61f0f197d845b09c7e84104288b6fd97f6fc0af08f54':
    raise RuntimeError('Compiler candidate source is no longer current')
shutil.copyfile(folder+'/PipelineValidation.Compiler.exe',probe+'/PipelineValidation.Compiler.exe')
shutil.copyfile(folder+'/PipelineValidation.Compiler.exe',baseline+'/PipelineValidation.Compiler.exe')
old_library=folder+'/before-compiler.so';old_hash=hashlib.sha256(open(old_library,'rb').read()).hexdigest()
if old_hash!='8709f01d6eb78e8b3c5767683d27fdeda175e340cc620084aa855e90ab91891e':raise RuntimeError('Incorrect compiler baseline library')
shutil.copyfile(old_library,baseline+'/libflighting_spinal_bridge.so')
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
         FLIGHTING_CITY_XY_CACHE='1',SPINAL_READBACK_BATCH='1')
samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
if len(samples)!=14:raise RuntimeError('Expected fourteen saved scenes')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    with open(folder+'/compiler-selected-reference.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',baseline+'/PipelineValidation.Compiler.exe']+samples,
                              env=dict(env,LD_LIBRARY_PATH=baseline,FLIGHTING_VALIDATION_OUT=reference,
                                       FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference'),stdout=log,stderr=log)
    expected=set([os.path.splitext(os.path.basename(p))[0]+'.argb' for p in samples]+['generated-%d.argb'%i for i in range(8)])
    actual=set(os.path.basename(p) for p in glob.glob(reference+'/*.argb'))
    if actual!=expected:raise RuntimeError('Incomplete cross-build pixel baseline')
    with open(folder+'/compiler-o3-cross-reference.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',probe+'/PipelineValidation.Compiler.exe']+samples,
                              env=dict(env,LD_LIBRARY_PATH=probe,FLIGHTING_VALIDATION_BASELINE_DIR=reference,
                                       FLIGHTING_VALIDATION_REQUIRE_BASELINE='1'),stdout=log,stderr=log)
    result=dict(passed=True,reference_scenes=22,frames_per_build=288,
                reference_hashes={name:hashlib.sha256(open(reference+'/'+name,'rb').read()).hexdigest() for name in sorted(expected)},
                selected_library_sha256=old_hash,candidate_library_sha256=hashlib.sha256(open(probe+'/libflighting_spinal_bridge.so','rb').read()).hexdigest())
    with open(folder+'/compiler-cross-reference.json','w') as f:json.dump(result,f,indent=2)
finally:
    after=hashes();subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=after:raise RuntimeError('Production sources or binaries changed')
print(json.dumps(dict(passed=True,production_unchanged=True,reference_scenes=22)))
