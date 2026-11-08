"""One-off recovery of the detected UNO's USB connection; no firmware writes."""
from __future__ import print_function
import ctypes as C,json,os,signal,subprocess,sys,time
os.chdir('/root/hackrpi');sys.path.insert(0,'combat/board');import arduino_usb as usb
pid=int(open('sensor.pid').read())
try:command=open('/proc/%d/cmdline'%pid,'rb').read()
except IOError:command=b''
if command:
    if b'combat/board/arduino_usb.py' not in command:raise RuntimeError('Unexpected sensor PID')
    os.kill(pid,signal.SIGTERM)
    for unused in range(100):
        try:
            if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
        except IOError:break
        time.sleep(.05)
    else:raise RuntimeError('Sensor reader did not stop')
result={};device=None
try:
    device=usb.CDC();device.lib.libusb_reset_device.argtypes=[C.c_void_p];device.lib.libusb_reset_device.restype=C.c_int
    result['port']=device.port;result['endpoint']=device.endpoint
    for label in ['before','after_clear']:
        status=C.create_string_buffer(2);n=device.lib.libusb_control_transfer(device.handle,0x82,0,0,device.endpoint,status,2,1000)
        result[label]=dict(status_result=n,bytes=list(bytearray(status.raw)))
        if label=='before':result['clear_halt']=device.lib.libusb_clear_halt(device.handle,device.endpoint)
    result['usb_reset']=device.lib.libusb_reset_device(device.handle)
finally:
    if device:device.close()
    null=open(os.devnull,'r');log=open('sensor.log','a')
    reader=subprocess.Popen(['python','combat/board/arduino_usb.py','--snapshot','/dev/shm/hackrpi-game/sensor.json'],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
    open('sensor.pid','w').write(str(reader.pid)+'\n');null.close();log.close()
time.sleep(4);result['snapshot']=json.load(open('/dev/shm/hackrpi-game/sensor.json'))
with open('build/software-profile/usb-recovery.json','w') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
