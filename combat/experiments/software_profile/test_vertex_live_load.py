"""Paused-scene A/B/A with the real USB reader and browser delivery load.

Not an active-play or displayed-FPS measurement. Restore the selected executable.
"""
from __future__ import print_function
import hashlib,json,os,shutil,subprocess,sys,time
from urllib2 import urlopen
sys.path.insert(0,'/root/hackrpi/fpga/software')
from legacy_host import monotonic

os.chdir('/root/hackrpi');folder='build/software-profile';exe='combat/dist/Flighting.Headless.exe';probe='/dev/shm/hackrpi-vertex-candidate'
def metrics():
    response=urlopen('http://127.0.0.1:8081/metrics',timeout=3)
    try:return json.load(response)
    finally:response.close()
def quiet(m):return m.get('simulation_paused',True) and not any(c.get('kind')=='browser' and c.get('visible') for c in m.get('display_clients',[]))
initial=metrics()
if not quiet(initial):raise RuntimeError('Leave an active/visible game controller alone')
expected_displays=len(initial.get('display_clients',[]))
before=hashlib.sha256(open(exe,'rb').read()).hexdigest()
if before!='c42205b3a28856372f6bc0f3540fbdc4862421353b24075a5808fc38b0b9a502':raise RuntimeError('This comparison requires the selected pre-vertex executable')
backup=probe+'/before-live-load.exe';shutil.copyfile(exe,backup)
env=dict(os.environ,FLIGHTING_DIRECT_VERTEX_BUFFER='1');results=[]
def install(path):shutil.copyfile(path,exe+'.next');os.rename(exe+'.next',exe)
def cpu_ticks(pid):
    fields=open('/proc/%d/stat'%pid).read().rsplit(') ',1)[1].split();return int(fields[11])+int(fields[12])
try:
    for label,path in [('vertex-load-before',backup),('vertex-load-direct',probe+'/VertexCandidate.exe'),('vertex-load-after',backup)]:
        subprocess.check_call(['python','combat/board/stop_service.py']);install(path)
        subprocess.check_call(['sh','combat/board/start_service.sh'],env=env)
        warmup=[];stable=0;warming=monotonic();samples=[]
        while monotonic()-warming<20:
            try:m=metrics()
            except (IOError,ValueError) as error:
                warmup.append(dict(seconds=monotonic()-warming,error=str(error)));stable=0;time.sleep(.5);continue
            if not quiet(m):raise RuntimeError('Human play began; restore the selected build')
            good=m.get('source')=='hardware' and not m.get('error') and m.get('sensor_fresh') and len(m.get('display_clients',[]))==expected_displays
            warmup.append(dict(seconds=monotonic()-warming,source=m.get('source'),error=m.get('error'),sensor_fresh=m.get('sensor_fresh'),displays=len(m.get('display_clients',[]))))
            stable=stable+1 if good else 0
            if stable>=3:break
            time.sleep(.5)
        with open(folder+'/'+label+'-warmup.json','w') as f:json.dump(warmup,f,indent=2)
        if stable<3:raise RuntimeError('Services did not become ready; inspect warmup diagnostics')
        pid=int(open('game.pid').read());cpu_start=cpu_ticks(pid);started=monotonic()
        while monotonic()-started<20.5:
            m=metrics()
            if not quiet(m):raise RuntimeError('Human play began; restore the selected build')
            if m.get('source')!='hardware' or m.get('error') or not m.get('sensor_fresh') or len(m.get('display_clients',[]))!=expected_displays:
                with open(folder+'/'+label+'-failure.json','w') as f:json.dump(m,f,indent=2)
                raise RuntimeError('Live services were not healthy; inspect saved diagnostics')
            samples.append(dict(seconds=monotonic(),metrics=m));time.sleep(.5)
        cpu_end=cpu_ticks(pid);first,last=samples[0],samples[-1];elapsed=last['seconds']-first['seconds']
        summary=dict(label=label,seconds=elapsed,completed_fps=(last['metrics']['gpu_sequence']-first['metrics']['gpu_sequence'])/elapsed,
                     collected_fps=(last['metrics']['frames_captured']-first['metrics']['frames_captured'])/elapsed,
                     game_cpu_percent=100*(cpu_end-cpu_start)/float(os.sysconf('SC_CLK_TCK'))/(monotonic()-started),
                     sensor_samples_per_second=(last['metrics']['sensor_samples']-first['metrics']['sensor_samples'])/elapsed,
                     triangle_counts=sorted(set(s['metrics']['triangles_submitted'] for s in samples)),
                     browser_counts=sorted(set(len(s['metrics']['display_clients']) for s in samples)),
                     all_paused=all(s['metrics']['simulation_paused'] for s in samples),
                     ticks=sorted(set(s['metrics']['tick'] for s in samples)))
        with open(folder+'/'+label+'.json','w') as f:json.dump(dict(summary=summary,samples=samples),f,indent=2)
        results.append(summary);print(json.dumps(summary));sys.stdout.flush()
finally:
    subprocess.check_call(['python','combat/board/stop_service.py']);install(backup)
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if hashlib.sha256(open(exe,'rb').read()).hexdigest()!=before:raise RuntimeError('Selected executable was not restored')
if any(s['ticks']!=[0] or not s['all_paused'] for s in results):raise RuntimeError('Static scene was not stable')
if len(set(tuple(s['triangle_counts']) for s in results))!=1:raise RuntimeError('Compared scenes had different triangle workloads')
with open(folder+'/vertex-live-load-summary.json','w') as f:json.dump(dict(paused_scene_only=True,production_restored=True,runs=results),f,indent=2)
print(json.dumps(dict(production_restored=True)))
