"""Bounded live test: inject one PIPE failure and recover the real USB link."""
from __future__ import print_function
import json,os,signal,subprocess,sys,time
os.chdir('/root/hackrpi');sys.path.insert(0,'combat/board');import arduino_usb as usb
pid=int(open('sensor.pid').read());command=open('/proc/%d/cmdline'%pid,'rb').read()
if b'combat/board/arduino_usb.py' not in command:raise RuntimeError('Unexpected reader PID')
os.kill(pid,signal.SIGTERM)
for unused in range(100):
    try:
        if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
    except IOError:break
    time.sleep(.05)
else:raise RuntimeError('Reader did not stop')
original_read=usb.CDC.read;original_reset=usb.CDC.reset_connection
injected=[False];resets=[0];sensor=None;result={}
def read(self):
    if not injected[0]:
        injected[0]=True
        raise usb.USBError(-9)
    return original_read(self)
def reset(self):
    resets[0]+=1
    return original_reset(self)
usb.CDC.read=read;usb.CDC.reset_connection=reset
try:
    sensor=usb.Sensor('/dev/shm/hackrpi-game/sensor.json');deadline=time.time()+10
    while time.time()<deadline:
        snapshot=sensor.snapshot()
        if snapshot['fresh'] and snapshot['count']>=5:break
        time.sleep(.1)
    result=dict(injected_pipe=injected[0],usb_resets=resets[0],fresh=snapshot['fresh'],samples=snapshot['count'],error=snapshot['error'])
finally:
    if sensor:sensor.close()
    null=open(os.devnull,'r');log=open('sensor.log','a')
    reader=subprocess.Popen(['python','combat/board/arduino_usb.py','--snapshot','/dev/shm/hackrpi-game/sensor.json'],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
    open('sensor.pid','w').write(str(reader.pid)+'\n');null.close();log.close()
    with open('build/software-profile/usb-recovery-validation.json','w') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
assert result['injected_pipe'] and result['usb_resets']==1 and result['fresh'] and result['samples']>=5 and result['error'] is None,'USB recovery check failed'
