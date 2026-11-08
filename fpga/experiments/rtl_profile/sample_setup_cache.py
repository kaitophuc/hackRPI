"""Isolated setup-write cache sample on the selected software and current FPGA."""
from __future__ import print_function
import hashlib,json,os,shutil,subprocess,sys
from urllib2 import urlopen
root='/root/hackrpi';os.chdir(root);out='/dev/shm/rtl-setup-cache'
if not os.path.isdir(out):os.mkdir(out)
library=root+'/combat/dist/libflighting_spinal_bridge.so'
def digest(path):return hashlib.sha256(open(path,'rb').read()).hexdigest()
before=digest(library)
if before!='515618d24ac54cc0ca10aca2df7a1d75574b7f7c2653a740764d1360e1b75dbd':raise RuntimeError('Unexpected selected native library')
response=urlopen('http://127.0.0.1:8081/metrics',timeout=3);status=json.load(response);response.close()
if not status.get('simulation_paused',True) or any(c.get('visible') for c in status.get('display_clients',[])):raise RuntimeError('A person is using the game')
source=open('combat/native/spinal_pipeline.c').read()
def change(old,new):
    global source
    if source.count(old)!=1:raise RuntimeError('Unexpected pipeline marker '+old)
    source=source.replace(old,new)
change('#include "spinal_bridge.c"','#include "/root/hackrpi/combat/native/spinal_bridge.c"')
change('int flighting_flat_colors;','int flighting_flat_colors;\nint flighting_cached_setup;\nstatic int pipe_cached_setup;')
change('    if(!flighting_flat_colors)flighting_color_epoch++;','    flighting_cached_setup=pipe_state.phase&&pipe_cached_setup;\n    if(!flighting_flat_colors)flighting_color_epoch++;')
change('    flighting_flat_colors=0;','    flighting_flat_colors=flighting_cached_setup=0;')
marker='    pipe_cached_colors=getenv("SPINAL_CACHE_COLORS")&&strcmp(getenv("SPINAL_CACHE_COLORS"),"1")==0;'
change(marker,marker+'\n    pipe_cached_setup=getenv("SPINAL_CACHE_SETUP")&&strcmp(getenv("SPINAL_CACHE_SETUP"),"1")==0;')
with open(out+'/spinal_pipeline.c','w') as f:f.write(source)
source=open('combat/native/spinal_color_cache.c').read()
def color(old,new):
    global source
    if source.count(old)!=1:raise RuntimeError('Unexpected color marker')
    source=source.replace(old,new)
color('extern int flighting_flat_colors;','extern int flighting_flat_colors;\nextern int flighting_cached_setup;')
color('static uint32_t cached[9];','static uint32_t cached[9];\nstatic unsigned setup_epoch,setup_valid;\nstatic uint32_t setup_bits[30];\nstatic uintptr_t setup_address[30];')
color('    if(flighting_flat_colors){','''    if(flighting_cached_setup&&offset>=0x88&&offset<=0xfc&&(offset&3)==0){
        unsigned slot=(offset-0x88)/4,mask=1u<<slot;uint32_t bits;memcpy(&bits,&value,sizeof(bits));
        if(setup_epoch!=flighting_color_epoch){setup_valid=0;setup_epoch=flighting_color_epoch;}
        if((setup_valid&mask)&&setup_address[slot]==(uintptr_t)address&&setup_bits[slot]==bits)return;
        setup_valid|=mask;setup_address[slot]=(uintptr_t)address;setup_bits[slot]=bits;
        *(volatile float *)address=value;return;
    }
    if(flighting_flat_colors){''')
with open(out+'/spinal_color_cache.c','w') as f:f.write(source)
build=open('combat/board/build_native.sh').read().replace('root=$(CDPATH= cd -- "$here/../.." && pwd)','root=/root/hackrpi')
build=build.replace('$root/combat/native/spinal_pipeline.c',out+'/spinal_pipeline.c').replace('$root/combat/native/spinal_color_cache.c',out+'/spinal_color_cache.c')
build=build.replace('$root/build/software-profile/cached-colors.o',out+'/cached-colors.o')
build=build.replace('$root/combat/dist/libflighting_spinal_bridge.so.next',out+'/libflighting_spinal_bridge.so')
build=build[:build.index('\nmv ')]+'\n'
process=subprocess.Popen(['sh','-s'],stdin=subprocess.PIPE);process.communicate(build)
if process.returncode:raise RuntimeError('Candidate compile failed')
env=dict(os.environ,SPINAL_READBACK_BATCH='1',SPINAL_CACHE_SETUP='1',FLIGHTING_PROFILE_DIR=out)
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    for label,so in [('before',library),('cached',out+'/libflighting_spinal_bridge.so'),('after',library)]:
        subprocess.check_call(['python',out+'/probe_setup_cost.py',so,label],env=env)
finally:
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if digest(library)!=before:raise RuntimeError('Selected software changed')
runs={label:json.load(open(out+'/'+label+'-setup-cost.json')) for label in ('before','cached','after')}
scenes=[]
for a,b,c in zip(runs['before']['scenes'],runs['cached']['scenes'],runs['after']['scenes']):
    if not(a['scene']==b['scene']==c['scene'] and a['pixel_hashes']==b['pixel_hashes']==c['pixel_hashes'] and len(a['pixel_hashes'])==1):raise RuntimeError('Scene pixels changed')
    scenes.append(dict(scene=a['scene'],before=a['median'],cached=b['median'],after=c['median'],pixels_identical=True))
result=dict(not_displayed_fps=True,production_unchanged=True,scenes=scenes)
with open(out+'/summary.json','w') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
