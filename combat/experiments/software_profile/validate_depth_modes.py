"""Cross-build pixel checks for restoring depth state after HUD/texture draws."""
from __future__ import print_function
import hashlib,json,os,shutil,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-depth-bypass';reference='/dev/shm/hackrpi-depth-mode-reference'
library='combat/dist/libflighting_spinal_bridge.so'
before=hashlib.sha256(open(library,'rb').read()).hexdigest()
if before!='41747a1c14eaf12936d4dffa75775c2650deb974f6e08e448603b8a772f7b3b8':raise RuntimeError('Depth-state baseline requires the pre-change compiler build')
shutil.copyfile(folder+'/DepthModeValidation.exe',probe+'/DepthModeValidation.exe')
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
         FLIGHTING_CITY_XY_CACHE='1',SPINAL_READBACK_BATCH='1')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    for label,exe,location,phase in [('depth-mode-before',folder+'/DepthModeValidation.exe','/root/hackrpi/combat/dist','capture'),
                                     ('depth-mode-bypass',probe+'/DepthModeValidation.exe',probe,'verify')]:
        with open(folder+'/'+label+'.log','w') as log:
            subprocess.check_call(['runtime/usr/bin/mono-sgen',exe,phase,reference],env=dict(env,LD_LIBRARY_PATH=location),stdout=log,stderr=log)
    hashes={name:hashlib.sha256(open(reference+'/'+name,'rb').read()).hexdigest() for name in sorted(os.listdir(reference)) if name.endswith('.argb')}
    if len(hashes)!=6:raise RuntimeError('Incomplete depth-mode reference')
    result=dict(passed=True,reference_scenes=6,queued_frames_per_build=72,reference_hashes=hashes,
                baseline_library_sha256=before,candidate_library_sha256=hashlib.sha256(open(probe+'/libflighting_spinal_bridge.so','rb').read()).hexdigest())
    with open(folder+'/depth-mode-validation.json','w') as f:json.dump(result,f,indent=2)
finally:
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if hashlib.sha256(open(library,'rb').read()).hexdigest()!=before:raise RuntimeError('Production library changed')
print(json.dumps(dict(passed=True,reference_scenes=6,queued_frames_per_build=72,production_unchanged=True)))
