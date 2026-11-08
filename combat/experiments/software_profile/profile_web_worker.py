"""Profile each server thread with its own CPU timer (Python 2.7 compatible)."""
import atexit,cProfile,ctypes,os,sys,threading
sys.path.insert(0,os.path.abspath('fpga/software'))
import server
class Timespec(ctypes.Structure):_fields_=[('seconds',ctypes.c_long),('nanos',ctypes.c_long)]
clock=ctypes.CDLL('librt.so.1').clock_gettime;clock.argtypes=[ctypes.c_int,ctypes.POINTER(Timespec)];clock.restype=ctypes.c_int
def cpu_time():
    value=Timespec();clock(3,ctypes.byref(value));return value.seconds+value.nanos/1e9
profiles=[];original=threading.Thread.run
def run(self):
    profile=cProfile.Profile(cpu_time);profiles.append((self.name,threading.current_thread().ident,profile))
    return profile.runcall(original,self)
threading.Thread.run=run
def save():
    for name,ident,profile in profiles:profile.dump_stats('build/software-profile/web-thread-%s-%s.pstats'%(name,ident))
atexit.register(save)
server.main()
