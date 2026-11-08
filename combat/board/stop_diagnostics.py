"""Stop only the known GPU diagnostic producer before taking its device lock."""
from __future__ import print_function
import os,signal,time
pid=int(open('/root/de10_gpu_platform/software/spinal-server.pid').read())
assert pid>1
path='/proc/%d/'%pid
if os.path.exists(path+'cmdline'):
    command=open(path+'cmdline','rb').read()
    if command:
        assert b'server.py' in command and b'spinal/spinal_capture' in command and b'8081' in command
        os.kill(pid,signal.SIGINT)
        for unused in range(50):
            try:
                state=open(path+'stat').read().rsplit(')',1)[1].split()[0]
                if state=='Z':break
            except IOError:break
            time.sleep(.1)
        else:raise RuntimeError('Diagnostic producer did not stop')
print('Diagnostic producer stopped; FPGA image unchanged')
