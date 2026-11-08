from __future__ import print_function
import hashlib,json,os,struct,subprocess,time
from urllib2 import urlopen
root='/root/hackrpi';out='/dev/shm/rtl-selected-cpu'
response=urlopen('http://127.0.0.1:8081/metrics',timeout=3);metrics=json.load(response);response.close()
if not metrics.get('simulation_paused',True):raise RuntimeError('Use a paused scene for this diagnostic')
pid=int(open(root+'/game.pid').read())
if 'Flighting.Headless.exe' not in open('/proc/%d/cmdline'%pid,'rb').read():raise RuntimeError('Unexpected game owner')
library=root+'/combat/dist/libflighting_spinal_bridge.so'
if hashlib.sha256(open(library,'rb').read()).hexdigest()!='515618d24ac54cc0ca10aca2df7a1d75574b7f7c2653a740764d1360e1b75dbd':raise RuntimeError('Unexpected native library')
if not os.path.isdir(out):os.mkdir(out)
subprocess.check_call(['cc','-O2',out+'/sample_cpu.c','-lrt','-o',out+'/sample_cpu'])
with open(out+'/rtl-game-maps.txt','w') as f:f.write(open('/proc/%d/maps'%pid).read())
with open(out+'/rtl-native-symbols.txt','w') as f:subprocess.check_call(['nm','-n',library],stdout=f)
threads={tid:open('/proc/%d/task/%s/comm'%(pid,tid)).read().strip() for tid in os.listdir('/proc/%d/task'%pid)}
with open(out+'/rtl-cpu-samples.csv','w') as f:subprocess.check_call([out+'/sample_cpu',str(pid)],stdout=f)
if pid!=int(open(root+'/game.pid').read()):raise RuntimeError('Game restarted during sampling')
result=dict(pid=pid,threads=threads,paused_scene=True,not_fps_benchmark=True,triangles=metrics.get('triangles_submitted'),tick=metrics.get('tick'))
with open(out+'/info.json','w') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
