"""Yield only after a complete sensor frame; retain original USB transfers.

An isolated A/B/A trial on one connection. It measures sample loss and relative
arrival lag as well as interrupts and paused-game throughput. Never flashes.
"""
from __future__ import print_function
import ctypes as C,json,os,signal,struct,subprocess,sys,time
os.chdir('/root/hackrpi');sys.path.insert(0,'combat/board');import arduino_usb as usb

def frame():
    with open('/dev/shm/hackrpi-game/frame.bin','rb') as f:
        size=struct.unpack('<4sIIII',f.read(20))[3];return json.loads(f.read(size))

def counters():
    cpu=list(map(int,open('/proc/stat').readline().split()[1:]));irq=0
    for line in open('/proc/interrupts'):
        if 'ffb40000.usb' in line:irq=sum(int(v) for v in line.split()[1:3])
    return sum(cpu),cpu[3]+cpu[4],irq

def percentile(values,p):
    values=sorted(values)
    return values[min(len(values)-1,int(len(values)*p))] if values else None

if not frame()['paused']:raise RuntimeError('Game must be paused for this comparison')
pid=int(open('sensor.pid').read());command=open('/proc/%d/cmdline'%pid,'rb').read()
if b'combat/board/arduino_usb.py' not in command:raise RuntimeError('Unexpected reader PID')
os.kill(pid,signal.SIGTERM)
for unused in range(100):
    try:
        if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
    except IOError:break
    time.sleep(.05)
else:raise RuntimeError('Reader did not stop')

observed=[];transfers=[];sensor=None;results=[]
original_accept=usb.Sensor.accept;original_init=usb.CDC.__init__
def accept(self,line):
    before=self.count;original_accept(self,line)
    if self.count!=before:
        now=time.time();observed.append((now,self.last_sequence,self.last_ms))
def initialize(self):
    original_init(self);bulk=self.lib.libusb_bulk_transfer
    def transfer(*args):
        start=time.time();result=bulk(*args);count=C.cast(args[4],C.POINTER(C.c_int))[0]
        transfers.append((time.time()-start,result,count))
        return result
    self.lib.libusb_bulk_transfer=transfer
usb.Sensor.accept=accept;usb.CDC.__init__=initialize
try:
    sensor=usb.Sensor('/dev/shm/hackrpi-game/sensor.json');limit=time.time()+8
    while not sensor.snapshot()['fresh'] and time.time()<limit:time.sleep(.1)
    if not sensor.snapshot()['fresh']:raise RuntimeError('No fresh samples for trial')
    lag_anchor=observed[-1][0]-observed[-1][2]/1000.
    for label,seconds in [('original-before',0),('after-frame150',.15),('original-after',0)]:
        sensor.frame_yield_ms=seconds*1000;time.sleep(.5)
        first=sensor.snapshot();begin_frame=frame();before=counters();start=time.time();a=len(observed);b=len(transfers)
        time.sleep(12)
        elapsed=time.time()-start;last=sensor.snapshot();end_frame=frame();after=counters();frames=observed[a:];reads=transfers[b:]
        lag=[1000*(received-ms/1000.-lag_anchor) for received,seq,ms in frames]
        result=dict(mode=label,seconds=elapsed,samples=last['count']-first['count'],fresh=last['fresh'],error=last['error'],
            generation_change=last['generation']-first['generation'],game_completed_fps=(end_frame['frame_sequence']-begin_frame['frame_sequence'])/elapsed,
            game_tick_change=end_frame['tick']-begin_frame['tick'],usb_irqs_per_second=(after[2]-before[2])/elapsed,
            cpu_busy_fraction=1.-float(after[1]-before[1])/(after[0]-before[0]),
            relative_lag_ms_median=percentile(lag,.5),relative_lag_ms_p95=percentile(lag,.95),
            read_calls=len(reads),read_median_ms=1000*percentile([r[0] for r in reads],.5) if reads else None,
            read_timeouts=sum(r[1]==-7 for r in reads),bytes_received=sum(r[2] for r in reads))
        if frames:
            span=frames[-1][1]-frames[0][1]+1
            result['sequence_span']=span;result['received_fraction']=len(frames)/float(span) if span>0 else None
        results.append(result);print(json.dumps(result));sys.stdout.flush()
        if not last['fresh'] or result['game_tick_change']:break
finally:
    if sensor:sensor.close()
    null=open(os.devnull,'r');log=open('sensor.log','a')
    reader=subprocess.Popen(['python','combat/board/arduino_usb.py','--snapshot','/dev/shm/hackrpi-game/sensor.json'],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
    open('sensor.pid','w').write(str(reader.pid)+'\n');null.close();log.close()
    with open('build/software-profile/usb-frame-yield-exact.json','w') as f:json.dump(results,f,indent=2)
