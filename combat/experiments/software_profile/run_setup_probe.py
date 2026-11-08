"""Build a separate RAM-only probe; never replace production source or library."""
from __future__ import print_function
import hashlib,json,os,subprocess,sys
os.chdir('/root/hackrpi');folder='build/software-profile'
source='combat/native/spinal_color_cache.c';library='combat/dist/libflighting_spinal_bridge.so'
def digest(path):
    with open(path,'rb') as f:return hashlib.sha256(f.read()).hexdigest()
before=dict(source=digest(source),library=digest(library))
text=open(source).read();marker='    *(volatile float *)address=value;'
if text.count(marker)!=1:raise RuntimeError('Unexpected setup-store source')
text=text.replace('static uint32_t cached[9];','static uint32_t cached[9];\nstatic volatile float probe_sink;')
text=text.replace(marker,'    probe_sink=value; /* DIAGNOSTIC ONLY: no triangle register write. */')
with open(folder+'/setup-ram-only.c','w') as f:f.write(text)
build=open('combat/board/build_native.sh').read()
root_line='root=$(CDPATH= cd -- "$here/../.." && pwd)'
if build.count(root_line)!=1:raise RuntimeError('Unexpected build root')
build=build.replace(root_line,'root=/root/hackrpi')
build=build.replace('$root/combat/native/spinal_color_cache.c','$root/build/software-profile/setup-ram-only.c')
build=build.replace('$root/build/software-profile/cached-colors.o','$root/build/software-profile/setup-ram-only.o')
build=build.replace('$root/combat/dist/libflighting_spinal_bridge.so.next','$root/build/software-profile/setup-ram-only.so')
build=build[:build.index('\nmv ')]+'\n'
process=subprocess.Popen(['sh','-s'],stdin=subprocess.PIPE)
process.communicate(build.encode('ascii'))
if process.returncode:raise RuntimeError('Probe build failed')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    for label,so in [('setup-v2-real-before',library),('setup-v2-ram-only',folder+'/setup-ram-only.so'),('setup-v2-real-after',library)]:
        subprocess.check_call(['python',folder+'/probe_setup_cost.py',so,label])
finally:
    after=dict(source=digest(source),library=digest(library))
    if before!=after:raise RuntimeError('Production source or binary changed unexpectedly')
    subprocess.check_call(['sh','combat/board/start_service.sh'])
print(json.dumps(dict(production_unchanged=before==after,hashes=after)))
