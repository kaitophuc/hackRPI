"""Compare read sizes on one CDC connection, without changing firmware.

The paused game keeps rendering. A reset of this USB connection at the start
recovers the known wedged endpoint; the original broker is restored on exit.
"""
from __future__ import print_function
import ctypes as C,json,os,signal,struct,subprocess,sys,time
os.chdir('/root/hackrpi');sys.path.insert(0,'combat/board')
import arduino_usb as usb

def frame():
    with open('/dev/shm/hackrpi-game/frame.bin','rb') as f:
        size=struct.unpack('<4sIIII',f.read(20))[3]
        return json.loads(f.read(size))

def counters():
    cpu=list(map(int,open('/proc/stat').readline().split()[1:]));irq=0
    for line in open('/proc/interrupts'):
        if 'ffb40000.usb' in line:irq=sum(int(v) for v in line.split()[1:3])
    return sum(cpu),cpu[3]+cpu[4],irq

pid=int(open('sensor.pid').read())
command=open('/proc/%d/cmdline'%pid,'rb').read()
if b'combat/board/arduino_usb.py' not in command:raise RuntimeError('Unexpected reader PID')
if not frame()['paused']:raise RuntimeError('Game must be paused for this comparison')
os.kill(pid,signal.SIGTERM)
for unused in range(100):
    try:
        if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
    except IOError:break
    time.sleep(.05)
else:raise RuntimeError('Reader did not stop')

settings=[512,0.];sequences=[];sensor=None;results=[]
original_accept=usb.Sensor.accept
def accept(self,line):
    before=self.count;original_accept(self,line)
    if self.count!=before:sequences.append(self.last_sequence)
usb.Sensor.accept=accept
def read(self):
    if settings[1]:time.sleep(settings[1])
    length=settings[0];buffer=C.create_string_buffer(length);count=C.c_int()
    result=self.lib.libusb_bulk_transfer(self.handle,self.endpoint,buffer,length,C.byref(count),200)
    if result==-9:
        if self.halt_recovered:self.check(result)
        self.check(self.lib.libusb_clear_halt(self.handle,self.endpoint));self.halt_recovered=True
        return b''
    if result not in (0,-7):self.check(result)
    if count.value:self.halt_recovered=False
    return buffer.raw[:count.value]
usb.CDC.read=read
try:
    device=usb.CDC()
    try:
        device.lib.libusb_reset_device.argtypes=[C.c_void_p];device.lib.libusb_reset_device.restype=C.c_int
        usb.CDC.check(device.lib.libusb_reset_device(device.handle))
    finally:device.close()
    sensor=usb.Sensor('/dev/shm/hackrpi-game/sensor.json');time.sleep(2)
    for name,length,pause in [('original',512,0),('packet64',64,0),('packet64-yield5',64,.005),('packet64-yield10',64,.010),('original-again',512,0)]:
        settings[:]=[length,pause];time.sleep(.5)
        first=sensor.snapshot();begin_frame=frame();before=counters();start=time.time();first_sequence=len(sequences)
        time.sleep(6)
        elapsed=time.time()-start;after=counters();last=sensor.snapshot();end_frame=frame();observed=sequences[first_sequence:]
        result=dict(mode=name,seconds=elapsed,samples=last['count']-first['count'],fresh=last['fresh'],error=last['error'],
            generation_change=last['generation']-first['generation'],game_completed_fps=(end_frame['frame_sequence']-begin_frame['frame_sequence'])/elapsed,
            game_tick_change=end_frame['tick']-begin_frame['tick'],usb_irqs_per_second=(after[2]-before[2])/elapsed,
            cpu_busy_fraction=1.-float(after[1]-before[1])/(after[0]-before[0]))
        if observed:
            span=observed[-1]-observed[0]+1
            result['sequence_span']=span;result['received_fraction']=len(observed)/float(span) if span>0 else None
        results.append(result);print(json.dumps(result));sys.stdout.flush()
        if not last['fresh']:break
finally:
    if sensor:sensor.close()
    null=open(os.devnull,'r');log=open('sensor.log','a')
    reader=subprocess.Popen(['python','combat/board/arduino_usb.py','--snapshot','/dev/shm/hackrpi-game/sensor.json'],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
    open('sensor.pid','w').write(str(reader.pid)+'\n');null.close();log.close()
    with open('build/software-profile/usb-continuous.json','w') as f:json.dump(results,f,indent=2)
