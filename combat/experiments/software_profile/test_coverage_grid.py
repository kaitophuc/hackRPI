"""Small coverage candidate: exact-image gates then bounded A/B/A timing."""
from __future__ import print_function
import glob,json,os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile';library='combat/dist/libflighting_spinal_bridge.so'
subprocess.check_call(['python','combat/board/stop_service.py'])
rollback=folder+'/before-half-coverage.so';shutil.copyfile(library,rollback)
source='combat/native/spinal_pipeline.c';original_source=open(source,'rb').read()
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
         FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference')
try:
    shutil.copyfile(folder+'/half-coverage-prototype.c',source)
    subprocess.check_call(['sh','combat/board/build_native.sh'])
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes')
    for label,enabled in [('coverage-reference','0'),('coverage-half','1')]:
        with open(folder+'/'+label+'-pixels.log','w') as log:
            subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Coverage.exe']+samples,env=dict(env,SPINAL_HALF_COVERAGE=enabled),stdout=log,stderr=log)
    for label,enabled in [('half-before','0'),('half-enabled','1'),('half-after','0')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],env=dict(env,SPINAL_HALF_COVERAGE=enabled))
finally:
    with open(source,'wb') as f:f.write(original_source)
    shutil.copyfile(rollback,library+'.next');os.rename(library+'.next',library)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(dict(production_restored=True)))
