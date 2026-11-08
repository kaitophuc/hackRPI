"""Validate general setup caching before profiling it; restore production."""
from __future__ import print_function
import glob,json,os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile';library='combat/dist/libflighting_spinal_bridge.so'
subprocess.check_call(['python','combat/board/stop_service.py'])
rollback=folder+'/before-setup-cache.so';shutil.copyfile(library,rollback)
sources=['combat/native/spinal_pipeline.c','combat/native/spinal_color_cache.c'];original_sources={p:open(p,'rb').read() for p in sources}
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',FLIGHTING_CITY_XY_CACHE='1',
         FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference')
try:
    for path in sources:shutil.copyfile(folder+'/setup-cache-prototype/'+os.path.basename(path),path)
    subprocess.check_call(['sh','combat/board/build_native.sh'])
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes')
    for label,enabled in [('setup-cache-off','0'),('setup-cache-on','1')]:
        with open(folder+'/'+label+'-pixels.log','w') as log:
            subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Coverage.exe']+samples,env=dict(env,SPINAL_CACHE_SETUP=enabled),stdout=log,stderr=log)
    for label,enabled in [('setup-cache-before','0'),('setup-cache-enabled','1'),('setup-cache-after','0')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],env=dict(env,SPINAL_CACHE_SETUP=enabled))
finally:
    for path,data in original_sources.items():
        with open(path,'wb') as f:f.write(data)
    shutil.copyfile(rollback,library+'.next');os.rename(library+'.next',library)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(dict(production_restored=True)))
