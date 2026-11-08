"""Validate the selected renderer while the real USB yield candidate is live."""
from __future__ import print_function
import glob,json,os,subprocess,time
os.chdir('/root/hackrpi');folder='build/software-profile'
subprocess.check_call(['python','combat/board/stop_service.py'])
sensor=None
try:
    null=open(os.devnull,'r');log=open('sensor.log','a')
    sensor=subprocess.Popen(['python','combat/board/arduino_usb.py','--frame-yield-ms','150','--snapshot','/dev/shm/hackrpi-game/sensor.json'],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
    open('sensor.pid','w').write(str(sensor.pid)+'\n');null.close();log.close()
    deadline=time.time()+10
    while True:
        before=json.load(open('/dev/shm/hackrpi-game/sensor.json'))
        if before.get('frame_yield_ms')==150 and before['fresh'] and before['count']>=3:break
        if time.time()>deadline:raise RuntimeError('Yield reader did not get fresh samples')
        time.sleep(.1)
    env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',LD_LIBRARY_PATH='/root/hackrpi/combat/dist',
             SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
             FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference',FLIGHTING_FRAME_FILE='/dev/shm/hackrpi-yield-validation.bin')
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes')
    with open(folder+'/sensor-yield-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',folder+'/PipelineValidation.Current.exe']+samples,env=env,stdout=log,stderr=log)
    after=json.load(open('/dev/shm/hackrpi-game/sensor.json'))
    result=dict(samples_received=after['count']-before['count'],generation_changes=after['generation']-before['generation'],sensor_fresh=after['fresh'],frame_yield_ms=after['frame_yield_ms'])
    with open(folder+'/sensor-yield-validation-health.json','w') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
    if not result['sensor_fresh'] or result['generation_changes'] or result['samples_received']<10:raise RuntimeError('Sensor was not healthy during pixel validation')
finally:
    # start_service gracefully stops this reader and restores the normal service.
    subprocess.check_call(['sh','combat/board/start_service.sh'])
