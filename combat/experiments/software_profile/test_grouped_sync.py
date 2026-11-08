"""Isolated pixel gate then A/B/A moving-game timing; restore live services."""
from __future__ import print_function
import glob,json,os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile'
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         LD_LIBRARY_PATH='/root/hackrpi/combat/dist',SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1')
subprocess.check_call(['python','combat/board/stop_service.py'])
library='combat/dist/libflighting_spinal_bridge.so';rollback=folder+'/before-grouped-sync.so';shutil.copyfile(library,rollback)
source='combat/native/spinal_pipeline.c';original_source=open(source,'rb').read()
passed=False
try:
    # Rejected prototype is an evidence artifact, never a production build input.
    shutil.copyfile(folder+'/grouped-sync-prototype.c',source)
    subprocess.check_call(['sh','combat/board/build_native.sh'])
    candidate=dict(env,SPINAL_GROUPED_SYNC='1',FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference')
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes, got %d'%len(samples))
    with open(folder+'/grouped-sync-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen','combat/dist/PipelineValidation.exe']+samples,env=candidate,stdout=log,stderr=log)
    for label,enabled in [('sync-before','0'),('sync-grouped','1'),('sync-after','0')]:
        print('PROFILE '+label);subprocess.check_call(['python',folder+'/profile_pipeline.py',label],env=dict(env,SPINAL_GROUPED_SYNC=enabled))
    passed=True
finally:
    # Keep the exact selected production binary until the candidate is reviewed.
    with open(source,'wb') as f:f.write(original_source)
    shutil.copyfile(rollback,library+'.next');os.rename(library+'.next',library)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(dict(pixel_gate_passed=passed,production_restored=True)))
