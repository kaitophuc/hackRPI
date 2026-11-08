"""Exact pixel gates and longer A/B/A runs for the readback scheduling policy."""
from __future__ import print_function
import glob,json,os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile';library='combat/dist/libflighting_spinal_bridge.so'
subprocess.check_call(['python','combat/board/stop_service.py'])
rollback=folder+'/before-readback-policy.so';shutil.copyfile(library,rollback)
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',FLIGHTING_CITY_XY_CACHE='1',
         FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference')
try:
    subprocess.check_call(['sh','combat/board/build_native.sh'])
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes')
    for label,enabled in [('readback-policy-off','0'),('readback-policy-on','1')]:
        with open(folder+'/'+label+'-pixels.log','w') as log:
            subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Coverage.exe']+samples,env=dict(env,SPINAL_READBACK_BATCH=enabled),stdout=log,stderr=log)
    for label,enabled in [('readback-policy-before','0'),('readback-policy-enabled','1'),('readback-policy-after','0')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],env=dict(env,SPINAL_READBACK_BATCH=enabled,FLIGHTING_PROFILE_TICKS='1200'))
        result=json.load(open(folder+'/'+label+'-pipeline.json'))
        active=[s['metrics'] for s in result['samples'] if 60<=s['metrics']['tick']<=1140]
        expected=3 if enabled=='1' else 0
        if not active or any(m.get('readback_policy')!=expected or m.get('readback_policy_error') for m in active):raise RuntimeError('Readback scheduling policy did not apply')
finally:
    shutil.copyfile(rollback,library+'.next');os.rename(library+'.next',library)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(dict(production_restored=True)))
