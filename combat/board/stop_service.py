from __future__ import print_function
import os,signal,time
ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'../..'))
def inspect(path,fragment):
    if not os.path.exists(path):return None
    pid=int(open(path).read());assert pid>1
    try:command=open('/proc/%d/cmdline'%pid,'rb').read()
    except IOError:return None
    if not command:return None
    if fragment not in command:raise RuntimeError('PID file points to another process: '+str(pid))
    return pid
def wait(pid):
    for unused in range(200):
        try:
            if open('/proc/%d/stat'%pid).read().rsplit(')',1)[1].split()[0]=='Z':return
        except IOError:return
        time.sleep(.1)
    raise RuntimeError('Process did not exit safely: '+str(pid))
game=inspect(ROOT+'/game.pid',b'Flighting.Headless.exe')
if game:
    open('/dev/shm/hackrpi-game/stop','w').close();wait(game)
web=inspect(ROOT+'/web.pid',b'fpga/software/server.py')
if web:os.kill(web,signal.SIGTERM);wait(web)
sensor=inspect(ROOT+'/sensor.pid',b'combat/board/arduino_usb.py')
if sensor:os.kill(sensor,signal.SIGTERM);wait(sensor)
print('Game, web and sensor services stopped safely')
