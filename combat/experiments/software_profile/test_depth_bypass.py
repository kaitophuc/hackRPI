"""Pixel-gate actual depth disabling for depth-free draws, then profile it."""
from __future__ import print_function
import glob,hashlib,json,os,shutil,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-depth-bypass';reference='/dev/shm/hackrpi-compiler-reference'
if not os.path.isdir(probe):os.mkdir(probe)
paths=['combat/dist/Flighting.Headless.exe','combat/dist/libflighting_spinal_bridge.so',
       'combat/native/spinal_pipeline.c','combat/native/spinal_color_cache.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes();source=open('combat/native/spinal_pipeline.c').read().replace('\r\n','\n')
if before['combat/native/spinal_pipeline.c']!='af6cc7865a927cef236a61f0f197d845b09c7e84104288b6fd97f6fc0af08f54':raise RuntimeError('Restore the pre-depth-bypass source before reproducing this experiment')
marker='TextureSlot *t;flighting_color_epoch++;grSstIdle();'
if source.count(marker)!=1:raise RuntimeError('Unexpected draw-state source')
source=source.replace(marker,marker+'grDepthBufferMode(d->depth?(wbuffer?GR_DEPTHBUFFER_WBUFFER:GR_DEPTHBUFFER_ZBUFFER):GR_DEPTHBUFFER_DISABLE);')
source=source.replace('#include "spinal_bridge.c"','#include "/root/hackrpi/combat/native/spinal_bridge.c"')
with open(probe+'/pipeline.c','w') as f:f.write(source)
build=open('combat/board/build_native.sh').read().replace('root=$(CDPATH= cd -- "$here/../.." && pwd)','root=/root/hackrpi')
build=build.replace('$root/combat/native/spinal_pipeline.c',probe+'/pipeline.c')
build=build.replace('$root/build/software-profile/cached-colors.o',probe+'/cached-colors.o')
build=build.replace('$root/combat/dist/libflighting_spinal_bridge.so.next',probe+'/libflighting_spinal_bridge.so')
build=build[:build.index('\nmv ')]+'\n'
process=subprocess.Popen(['sh','-s'],stdin=subprocess.PIPE);process.communicate(build.encode('ascii'))
if process.returncode:raise RuntimeError('Isolated depth-bypass build failed')
for exe in ['combat/dist/Flighting.Headless.exe',folder+'/PipelineValidation.Compiler.exe']:
    shutil.copyfile(exe,probe+'/'+os.path.basename(exe))
manifest=json.load(open(folder+'/compiler-cross-reference.json'))
if len(manifest['reference_hashes'])!=22:raise RuntimeError('Incomplete references')
for name,digest in manifest['reference_hashes'].items():
    if hashlib.sha256(open(reference+'/'+name,'rb').read()).hexdigest()!=digest:raise RuntimeError('Reference pixels changed')
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
         FLIGHTING_CITY_XY_CACHE='1',SPINAL_READBACK_BATCH='1',FLIGHTING_PROFILE_TICKS='1200',
         FLIGHTING_VALIDATION_BASELINE_DIR=reference,FLIGHTING_VALIDATION_REQUIRE_BASELINE='1')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes')
    with open(folder+'/depth-bypass-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',probe+'/PipelineValidation.Compiler.exe']+samples,
                              env=dict(env,LD_LIBRARY_PATH=probe),stdout=log,stderr=log)
    for label,location in [('depth-before','/root/hackrpi/combat/dist'),('depth-bypass',probe),('depth-after','/root/hackrpi/combat/dist')]:
        subprocess.check_call(['python',folder+'/probe_setup_cost.py',location+'/libflighting_spinal_bridge.so',label],
                              env=dict(env,LD_LIBRARY_PATH=location))
    for label,location in [('depth-before','/root/hackrpi/combat/dist'),('depth-bypass',probe),('depth-after','/root/hackrpi/combat/dist')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],
                              env=dict(env,LD_LIBRARY_PATH=location,FLIGHTING_PROFILE_EXE=location+'/Flighting.Headless.exe'))
finally:
    after=hashes();subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=after:raise RuntimeError('Production source or binary changed')
print(json.dumps(dict(production_unchanged=True,hashes=after)))
