"""Repeat the failing checkpoint with unchanged and stronger sync spacing."""
from __future__ import print_function
import json,os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile';library='combat/dist/libflighting_spinal_bridge.so'
subprocess.check_call(['python','combat/board/stop_service.py'])
rollback=folder+'/before-coverage-diagnosis.so';shutil.copyfile(library,rollback);results=[]
source='combat/native/spinal_pipeline.c';original_source=open(source,'rb').read()
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
         FLIGHTING_VALIDATION_REPEATS='200',FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference')
try:
    shutil.copyfile(folder+'/half-coverage-prototype.c',source)
    subprocess.check_call(['sh','combat/board/build_native.sh'])
    for label,enabled,syncs in [('focus-original-3','0','3'),('focus-half-3','1','3'),('focus-half-4','1','4')]:
        with open(folder+'/'+label+'-pixels.log','w') as log:
            code=subprocess.call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Coverage.exe',folder+'/samples/tick-600.rpl'],env=dict(env,SPINAL_HALF_COVERAGE=enabled,SPINAL_PIPELINE_SYNCS=syncs),stdout=log,stderr=log)
        result=dict(name=label,exit_code=code);results.append(result);print(json.dumps(result))
finally:
    with open(source,'wb') as f:f.write(original_source)
    shutil.copyfile(rollback,library+'.next');os.rename(library+'.next',library)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
with open(folder+'/coverage-sync-diagnosis.json','w') as f:json.dump(results,f,indent=2)
