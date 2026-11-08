from __future__ import print_function
import json,sys,time
try:from urllib.request import urlopen
except ImportError:from urllib2 import urlopen
samples=[];deadline=time.time()+40
while len(samples)<13:
    if time.time()>deadline:raise RuntimeError('No usable metrics within 40 seconds')
    start=time.time()
    response=urlopen('http://169.254.170.29:8081/metrics',timeout=3);m=json.load(response);response.close()
    if 'gpu_sequence' in m:samples.append(dict(seconds=start,metrics=m))
    time.sleep(max(0,1-(time.time()-start)))
first,last=samples[0],samples[-1];seconds=last['seconds']-first['seconds']
summary=dict(label=sys.argv[1],seconds=seconds,completed_fps=(last['metrics']['gpu_sequence']-first['metrics']['gpu_sequence'])/seconds,
             collected_fps=(last['metrics']['frames_captured']-first['metrics']['frames_captured'])/seconds,first_tick=first['metrics']['tick'],last_tick=last['metrics']['tick'],clients=last['metrics']['display_clients'])
with open('build/software-profile/'+sys.argv[1]+'.json','w') as f:json.dump(dict(summary=summary,samples=samples),f,indent=2)
print(json.dumps(summary,indent=2))
