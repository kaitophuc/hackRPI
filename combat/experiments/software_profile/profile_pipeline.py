"""Bounded moving full-game pipeline benchmark on the board, no web client."""
from __future__ import print_function
import json,os,shutil,struct,subprocess,sys,time
name=sys.argv[1];root='/root/hackrpi';folder=os.environ.get('FLIGHTING_PROFILE_DIR',root+'/build/software-profile');frame='/dev/shm/hackrpi-profile-'+name+'.bin'
ticks=int(os.environ.get('FLIGHTING_PROFILE_TICKS','600'))
if ticks<120 or ticks>1800:raise RuntimeError('Profile ticks must be 120..1800')
try:os.unlink(frame)
except OSError:pass
env=dict(os.environ,MONO_CFG_DIR=root+'/runtime/etc',MONO_PATH=root+'/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH=os.environ.get('LD_LIBRARY_PATH',root+'/combat/dist'),SPINAL_WBUFFER='1',FLIGHTING_PIPELINE='1',FLIGHTING_PACKED_REUSE='0' if name=='baseline' else '1',FLIGHTING_CITY_XY_CACHE=os.environ.get('FLIGHTING_CITY_XY_CACHE','1'),FLIGHTING_FRAME_FILE=frame)
env.pop('FLIGHTING_STOP_FILE',None)
log=open(folder+'/'+name+'-game.log','w')
command=[root+'/runtime/usr/bin/mono-sgen',os.environ.get('FLIGHTING_PROFILE_EXE',root+'/combat/dist/Flighting.Headless.exe'),'--backend','spinal','--headless','--realtime','--scripted','--ticks',str(ticks),'--complexity','18','--quality','low','--fps','30','--out',folder+'/'+name+'-last.ppm']
if 'managed-sample' in name:command.insert(1,'--jitmap')
process=subprocess.Popen(command,env=env,stdout=log,stderr=log);samples=[];sequence=None;started=time.time();pinned=False;sampler=None;sample_log=None;sampled=False
try:
    while process.poll() is None:
        if time.time()-started>60:raise RuntimeError('Bounded profile exceeded 60 seconds')
        if 'affinity' in name and not pinned:
            tasks={}
            try:
                for tid in os.listdir('/proc/%d/task'%process.pid):tasks[int(tid)]=open('/proc/%d/task/%s/comm'%(process.pid,tid)).read().strip()
            except IOError:pass
            if 'game-geometry' in tasks.values():
                for tid,thread_name in tasks.items():
                    core=1 if tid==process.pid or ('copy-main' in name and thread_name=='mono-sgen') else 0
                    subprocess.check_call(['taskset','-p','-c',str(core),str(tid)],stdout=log,stderr=log)
                pinned=True
        try:
            with open(frame,'rb') as f:
                header=f.read(20);magic,w,h,size,pixels=struct.unpack('<4sIIII',header);data=json.loads(f.read(size))
            if data['frame_sequence']!=sequence:
                sequence=data['frame_sequence'];samples.append(dict(seconds=time.time()-started,metrics=data))
                if 'managed-sample' in name and sampler is None and data['tick']>=120:
                    sample_log=open(folder+'/managed-cpu-samples.csv','w');sampler=subprocess.Popen([folder+'/sample_cpu',str(process.pid)],stdout=sample_log)
                if sampler is not None and sampler.poll() is not None and not sampled:
                    sample_log.close();shutil.copyfile('/tmp/perf-%d.map'%process.pid,folder+'/managed-game-jit.map');shutil.copyfile('/proc/%d/maps'%process.pid,folder+'/managed-game-maps.txt')
                    with open(folder+'/managed-native-symbols.txt','w') as symbols:subprocess.check_call(['nm','-n',root+'/combat/dist/libflighting_spinal_bridge.so'],stdout=symbols)
                    sampled=True
        except (IOError,ValueError,struct.error):pass
        time.sleep(.01)
finally:
    if process.poll() is None:
        process.terminate();process.wait()
    log.close()
    if sampler is not None and sampler.poll() is None:sampler.wait();sample_log.close()
if process.returncode:raise RuntimeError('Game profile failed; inspect '+name+'-game.log')
active=[s for s in samples if 60<=s['metrics']['tick']<=ticks-60]
if len(active)<2:raise RuntimeError('No meaningful moving frames captured')
elapsed=active[-1]['seconds']-active[0]['seconds'];summary=dict(name=name,frames=len(active),seconds=elapsed,completed_fps=(len(active)-1)/elapsed,first_tick=active[0]['metrics']['tick'],last_tick=active[-1]['metrics']['tick'],affinity_applied=pinned)
for field in ['geometry_ms','prepare_ms','host_submit_ms','copy_seconds','command_submit_ms','drain_ms','slot_wait_ms','owner_cpu_ms','previous_publish_ms','ready_wait_ms','scene_wait_ms','geometry_cpu_ms','prepare_cpu_ms','previous_submit_ms']:
    values=sorted(s['metrics'][field]*(1000 if field=='copy_seconds' else 1) for s in active if field in s['metrics'])
    if values:summary[field]=dict(median=values[len(values)//2],p95=values[int(len(values)*.95)],maximum=values[-1])
with open(folder+'/'+name+'-pipeline.json','w') as f:json.dump(dict(summary=summary,samples=samples),f,indent=2)
print(json.dumps(summary,indent=2))
