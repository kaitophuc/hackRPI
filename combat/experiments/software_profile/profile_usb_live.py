"""Run controlled USB-yield experiments with the paused game left rendering."""
from __future__ import print_function
import json,os,signal,subprocess,time
os.chdir('/root/hackrpi');pid=int(open('sensor.pid').read());command=open('/proc/%d/cmdline'%pid,'rb').read()
if b'combat/board/arduino_usb.py' not in command:raise RuntimeError('Unexpected reader PID')
os.kill(pid,signal.SIGTERM)
for unused in range(100):
    try:
        if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
    except IOError:break
    time.sleep(.05)
else:raise RuntimeError('Reader did not stop')
results=[]
try:
    for mode in ['original','yield5','yield10','yield20']:
        output=subprocess.check_output(['python','build/software-profile/profile_usb.py',mode],env=dict(os.environ,PROFILE_PUBLISH='1'));print(output.decode().strip());results.append(json.loads(output))
finally:
    null=open(os.devnull,'r');log=open('sensor.log','a');reader=subprocess.Popen(['python','combat/board/arduino_usb.py','--snapshot','/dev/shm/hackrpi-game/sensor.json'],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
    open('sensor.pid','w').write(str(reader.pid)+'\n');null.close();log.close()
with open('build/software-profile/usb-yield-live.json','w') as f:json.dump(results,f,indent=2)
