"""Stop only the known GPU diagnostic producer before taking its device lock."""
from __future__ import print_function
import argparse,os,signal,time

def stop(pid_file):
    # The old diagnostic installation is optional on a fresh recovery.
    if not os.path.isfile(pid_file):return
    pid=int(open(pid_file).read())
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

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid-file',default='/root/de10_gpu_platform/software/spinal-server.pid')
    stop(parser.parse_args().pid_file)
    print('Diagnostic producer stopped or absent; FPGA image unchanged')
