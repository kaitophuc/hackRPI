"""Pixel-gate and profile an isolated O3 native library, then restore services."""
from __future__ import print_function
import glob,hashlib,json,os,shutil,subprocess

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-compiler-o3';baseline='/dev/shm/hackrpi-compiler-baseline'
if not os.path.isdir(probe):os.mkdir(probe)
if not os.path.isdir(baseline):os.mkdir(baseline)
paths=['combat/dist/Flighting.Headless.exe','combat/dist/libflighting_spinal_bridge.so',
       'combat/native/spinal_pipeline.c','combat/native/spinal_color_cache.c','combat/board/build_native.sh']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes()
if before['combat/native/spinal_pipeline.c']!='af6cc7865a927cef236a61f0f197d845b09c7e84104288b6fd97f6fc0af08f54':raise RuntimeError('Compiler test requires its pinned pipeline source')
old_library=folder+'/before-compiler.so';old_build=folder+'/before-compiler-build_native.sh'
if hashlib.sha256(open(old_library,'rb').read()).hexdigest()!='8709f01d6eb78e8b3c5767683d27fdeda175e340cc620084aa855e90ab91891e':raise RuntimeError('Incorrect compiler baseline library')
if hashlib.sha256(open(old_build,'rb').read()).hexdigest()!='dfe67c7d94abfc4fe9fb27b06d251307b1a18153ae8851a74e76a4a71613ab2d':raise RuntimeError('Incorrect compiler baseline flags')
shutil.copyfile(old_library,baseline+'/libflighting_spinal_bridge.so')
shutil.copyfile('combat/dist/Flighting.Headless.exe',baseline+'/Flighting.Headless.exe')
build=open(old_build).read().replace('root=$(CDPATH= cd -- "$here/../.." && pwd)','root=/root/hackrpi')
if build.count('-O2')!=2:raise RuntimeError('Unexpected compiler configuration')
build=build.replace('-O2','-O3').replace('-march=armv7-a','-mcpu=cortex-a9 -mfpu=neon -ffp-contract=off')
build=build.replace('$root/build/software-profile/cached-colors.o',probe+'/cached-colors.o')
build=build.replace('$root/combat/dist/libflighting_spinal_bridge.so.next',probe+'/libflighting_spinal_bridge.so')
build=build[:build.index('\nmv ')]+'\n'
process=subprocess.Popen(['sh','-s'],stdin=subprocess.PIPE);process.communicate(build.encode('ascii'))
if process.returncode:raise RuntimeError('Isolated compiler build failed')
for exe in ['combat/dist/Flighting.Headless.exe',folder+'/PipelineValidation.Coverage.exe']:
    shutil.copyfile(exe,probe+'/'+os.path.basename(exe))
env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
         SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',
         FLIGHTING_CITY_XY_CACHE='1',SPINAL_READBACK_BATCH='1',FLIGHTING_PROFILE_TICKS='1200',
         FLIGHTING_VALIDATION_BASELINE_DIR='/root/hackrpi/build/software-profile/hardware-reference')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen reference scenes')
    with open(folder+'/compiler-o3-pixels.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',probe+'/PipelineValidation.Coverage.exe']+samples,
                              env=dict(env,LD_LIBRARY_PATH=probe),stdout=log,stderr=log)
    for label,location in [('compiler-before',baseline),('compiler-o3',probe),('compiler-after',baseline)]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],
                              env=dict(env,LD_LIBRARY_PATH=location,FLIGHTING_PROFILE_EXE=location+'/Flighting.Headless.exe'))
finally:
    after=hashes()
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=after:raise RuntimeError('Production source or binary changed')
print(json.dumps(dict(production_unchanged=True,hashes=after)))
