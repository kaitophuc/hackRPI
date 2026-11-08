from __future__ import print_function
import os,signal,subprocess,sys,time
os.chdir('/root/hackrpi');pid=int(open('web.pid').read())
try:command=open('/proc/%d/cmdline'%pid,'rb').read()
except IOError:command=b''
if command:
    if b'fpga/software/server.py' not in command:raise RuntimeError('Unexpected web PID')
    os.kill(pid,signal.SIGTERM)
for unused in range(100):
    try:
        if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
    except IOError:break
    time.sleep(.05)
else:raise RuntimeError('Web did not stop')
args=['python','fpga/software/server.py','--game-frame','/dev/shm/hackrpi-game/frame.bin','--game-input-port','5522','--bind','0.0.0.0','--port','8081','--fps','60']
env=dict(os.environ,GPU_CLOCK_KEEP_GIL=sys.argv[1]);null=open(os.devnull,'r');log=open('web.log','a')
process=subprocess.Popen(args,env=env,stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
open('web.pid','w').write(str(process.pid)+'\n');print('Restarted web PID',process.pid,'clock_keep_gil',sys.argv[1])
