"""Check exact reference hashes, then isolated ARM geometry A/B/A timings."""
from __future__ import print_function
import json,os,re,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile'
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist')
def run(label,exe,mode,count,enabled):
    path=folder+'/'+label+'.log'
    with open(path,'w') as log:subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/'+exe,mode,str(count)],env=dict(env,FLIGHTING_CITY_XY_CACHE=enabled),stdout=log,stderr=log)
    return open(path).read()
subprocess.check_call(['python','combat/board/stop_service.py'])
results={}
try:
    before=run('xy-reference-before','BeforeXY.exe','reference',600,'0')
    after=run('xy-reference-after','XYCache.exe','reference',600,'1')
    old=[line for line in before.splitlines() if line.startswith('REFERENCE ')]
    new=[line for line in after.splitlines() if line.startswith('REFERENCE ')]
    results['reference_checkpoints']=len(old);results['reference_hashes_identical']=old==new and len(old)==7
    if not results['reference_hashes_identical']:raise RuntimeError('Geometry or CPU reference hash changed')
    results['timings']={}
    for label,enabled in [('xy-before','0'),('xy-enabled','1'),('xy-after','0')]:
        text=run(label,'XYCache.exe','geometry',300,enabled)
        values={key:float(value) for key,value in re.findall(r'(median_ms|p95_ms|cpu_ms|retained_bytes)=([0-9.]+)',text)}
        results['timings'][label]=values;print(json.dumps(dict(label=label,measurements=values)))
finally:
    with open(folder+'/xy-cache-results.json','w') as f:json.dump(results,f,indent=2)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(results,indent=2))
