"""Briefly profile the existing board web service, then restore its normal command."""
from __future__ import print_function
import glob,os,signal,subprocess,time,pstats
root='/root/hackrpi';os.chdir(root);pid=int(open('web.pid').read())
if b'fpga/software/server.py' not in open('/proc/%d/cmdline'%pid,'rb').read():raise RuntimeError('Unexpected web PID')
os.kill(pid,signal.SIGTERM)
for unused in range(100):
    if not os.path.exists('/proc/%d'%pid) or open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':break
    time.sleep(.05)
else:raise RuntimeError('Web service did not stop')
args=['fpga/software/server.py','--game-frame','/dev/shm/hackrpi-game/frame.bin','--game-input-port','5522','--bind','0.0.0.0','--port','8081','--fps','60']
null=open(os.devnull,'r');log=open('build/software-profile/profile-web.log','w')
process=subprocess.Popen(['python','build/software-profile/profile_web_worker.py']+args[1:],stdin=null,stdout=log,stderr=log,preexec_fn=os.setsid)
open('web.pid','w').write(str(process.pid)+'\n')
try:time.sleep(12)
finally:
    process.send_signal(signal.SIGTERM);process.wait();log.close()
    normal_log=open('web.log','a')
    normal=subprocess.Popen(['python']+args,stdin=null,stdout=normal_log,stderr=normal_log,preexec_fn=os.setsid)
    open('web.pid','w').write(str(normal.pid)+'\n');normal_log.close();null.close()
files=glob.glob('build/software-profile/web-thread-*.pstats')
for path in files:
    print(path);pstats.Stats(path).strip_dirs().sort_stats('time').print_stats(12)
