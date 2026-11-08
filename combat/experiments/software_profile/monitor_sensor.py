"""Bounded sensor-health observation while the normal game is running."""
from __future__ import print_function
import json,os,time
samples=[];started=time.time()
for index in range(450):
    time.sleep(max(0,started+index*.1-time.time()))
    with open('/dev/shm/hackrpi-game/sensor.json') as f:
        s=json.load(f);modified=os.fstat(f.fileno()).st_mtime
    age=None if s['age'] is None else s['age']+max(0,time.time()-modified)
    samples.append(dict(seconds=time.time()-started,count=s['count'],generation=s['generation'],fresh=s['fresh'] and age is not None and age<=.75,error=s['error'],age=age,frame_yield_ms=s.get('frame_yield_ms',0)))
result=dict(seconds=samples[-1]['seconds'],observations=len(samples),fresh_observations=sum(bool(s['fresh']) for s in samples),
            generation_changes=samples[-1]['generation']-samples[0]['generation'],samples_advanced=samples[-1]['count']-samples[0]['count'],
            maximum_age=max(s['age'] for s in samples if s['age'] is not None),frame_yield_ms=sorted(set(s['frame_yield_ms'] for s in samples)))
with open('/root/hackrpi/build/software-profile/final-sensor-health.json','w') as f:json.dump(dict(summary=result,samples=samples),f,indent=2)
print(json.dumps(result))
