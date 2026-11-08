"""Check original-commit ARM CPU images and live FPGA images before deployment."""
from __future__ import print_function
import json,os,re,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile'
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1')
subprocess.check_call(['python','combat/board/stop_service.py'])
results={}
try:
    with open(folder+'/xy-commit-arm-reference.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen','combat/dist/Reference.exe','reference','600'],env=env,stdout=log,stderr=log)
    def rows(path):
        return [dict(re.findall(r'(tick|geometry|pixels)=([^ ]+)',line)) for line in open(path) if line.startswith('REFERENCE ')]
    original=rows(folder+'/xy-commit-arm-reference.log');cached=rows(folder+'/xy-reference-after.log')
    results['commit_cpu_images_equal']=len(original)==7 and [r['pixels'] for r in original]==[r['pixels'] for r in cached]
    results['commit_geometry_equal']=len(original)==7 and [r['geometry'] for r in original]==[r['geometry'] for r in cached]
    if not results['commit_cpu_images_equal']:raise RuntimeError('Original-commit CPU image changed')
    with open(folder+'/xy-cache-gpu-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/CompareProjectionCache.exe'],env=env,stdout=log,stderr=log)
    results['fpga_pixel_gate_passed']=True
finally:
    with open(folder+'/xy-cache-validation.json','w') as f:json.dump(results,f,indent=2)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(results,indent=2))
