"""Compare bounded USB polling with the original long outstanding bulk read."""
from __future__ import print_function
import ctypes as C,json,os,resource,struct,sys,time
sys.path.insert(0,os.path.abspath('combat/board'))
import arduino_usb as usb

def counters():
    cpu=list(map(int,open('/proc/stat').readline().split()[1:]));irq=0
    for line in open('/proc/interrupts'):
        if 'ffb40000.usb' in line:irq=sum(int(v) for v in line.split()[1:3])
    return sum(cpu),cpu[3]+cpu[4],irq

if len(sys.argv)>1 and sys.argv[1]=='polled':
    def read(self):
        time.sleep(.04)
        buffer=C.create_string_buffer(512);count=C.c_int()
        result=self.lib.libusb_bulk_transfer(self.handle,self.endpoint,buffer,512,C.byref(count),5)
        if result not in (0,-7):self.check(result)
        return buffer.raw[:count.value]
    usb.CDC.read=read
if sys.argv[1].startswith('yield'):
    original_read=usb.CDC.read;pause=float(sys.argv[1][5:])/1000
    def read(self):time.sleep(pause);return original_read(self)
    usb.CDC.read=read
sequences=[];original_accept=usb.Sensor.accept
def accept(self,line):
    before=self.count;original_accept(self,line)
    if self.count!=before:sequences.append(self.last_sequence)
usb.Sensor.accept=accept
def frame():
    with open('/dev/shm/hackrpi-game/frame.bin','rb') as f:
        header=f.read(20);size=struct.unpack('<4sIIII',header)[3];return json.loads(f.read(size))
publish=os.environ.get('PROFILE_PUBLISH')=='1';first_frame=frame() if publish else None
before=counters();usage=resource.getrusage(resource.RUSAGE_SELF);start=time.time();sensor=usb.Sensor('/dev/shm/hackrpi-game/sensor.json' if publish else None)
time.sleep(6);snapshot=sensor.snapshot();sensor.close();elapsed=time.time()-start
after=counters();last=resource.getrusage(resource.RUSAGE_SELF)
result=dict(mode=sys.argv[1],seconds=elapsed,samples=snapshot['count'],fresh=snapshot['fresh'],error=snapshot['error'],
    usb_irqs_per_second=(after[2]-before[2])/elapsed,cpu_busy_fraction=1.-float(after[1]-before[1])/(after[0]-before[0]),
    process_cpu_seconds=last.ru_utime+last.ru_stime-usage.ru_utime-usage.ru_stime)
if sequences:result['sequence_span']=sequences[-1]-sequences[0]+1;result['received_fraction']=len(sequences)/float(result['sequence_span'])
if publish:
    last_frame=frame();result['game_completed_fps']=(last_frame['frame_sequence']-first_frame['frame_sequence'])/elapsed;result['game_tick_change']=last_frame['tick']-first_frame['tick']
print(json.dumps(result,sort_keys=True))
