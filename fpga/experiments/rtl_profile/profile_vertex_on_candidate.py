"""Recheck the isolated CPU vertex prototype with the pipelined depth reader.

Run on the board. Services are restored and production binaries stay unchanged.
This is a controlled scripted sample, not a displayed-FPS measurement.
"""
from __future__ import print_function
import glob,hashlib,json,os,subprocess,sys
from urllib2 import urlopen

root='/root/hackrpi';os.chdir(root)
folder='/dev/shm/rtl-cpu-profile';probe='/dev/shm/hackrpi-vertex-candidate'
if not os.path.isdir(folder):os.mkdir(folder)
response=urlopen('http://127.0.0.1:8081/metrics',timeout=3)
status=json.load(response);response.close()
if not status.get('simulation_paused',True) or any(c.get('kind')=='browser' and c.get('visible') for c in status.get('display_clients',[])):
    raise RuntimeError('A person is using the game; leave services running')
paths=['combat/dist/Flighting.Headless.exe','combat/dist/libflighting_spinal_bridge.so','combat/native/spinal_pipeline.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes()
if before[paths[0]]!='c42205b3a28856372f6bc0f3540fbdc4862421353b24075a5808fc38b0b9a502' or before[paths[1]]!='515618d24ac54cc0ca10aca2df7a1d75574b7f7c2653a740764d1360e1b75dbd':
    raise RuntimeError('Unexpected selected software')
env=dict(os.environ,MONO_CFG_DIR=root+'/runtime/etc',MONO_PATH=root+'/runtime/usr/lib/mono/4.5',
         LD_LIBRARY_PATH=root+'/combat/dist',SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',
         SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',FLIGHTING_CITY_XY_CACHE='1',
         SPINAL_READBACK_BATCH='1',FLIGHTING_DIRECT_VERTEX_BUFFER='1',FLIGHTING_PROFILE_TICKS='1200',
         FLIGHTING_PROFILE_DIR=folder)
for manifest_path,directory,count in [('build/software-profile/compiler-cross-reference.json','/dev/shm/hackrpi-compiler-reference',22),
                                      ('build/software-profile/depth-mode-validation.json','/dev/shm/hackrpi-depth-mode-reference',6)]:
    manifest=json.load(open(manifest_path))
    if not manifest.get('passed') or len(manifest['reference_hashes'])!=count:raise RuntimeError('Incomplete pixel references')
    for name,digest in manifest['reference_hashes'].items():
        if hashlib.sha256(open(directory+'/'+name,'rb').read()).hexdigest()!=digest:raise RuntimeError('Pixel reference changed')
def run(label,exe,args,extra=None):
    with open(folder+'/'+label+'.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',exe]+args,env=dict(env,**(extra or {})),stdout=log,stderr=log)
    print(label+' passed');sys.stdout.flush()
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    samples=sorted(glob.glob('build/software-profile/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen saved scenes')
    run('vertex-pixels',probe+'/VertexPixels.exe',samples,dict(FLIGHTING_VALIDATION_BASELINE_DIR='/dev/shm/hackrpi-compiler-reference',FLIGHTING_VALIDATION_REQUIRE_BASELINE='1'))
    run('vertex-depth-modes',probe+'/VertexDepthModes.exe',['verify','/dev/shm/hackrpi-depth-mode-reference'])
    for label,exe in [('prepare-before',probe+'/BeforeVertexProfile.exe'),('prepare-direct',probe+'/VertexProfile.exe'),('prepare-after',probe+'/BeforeVertexProfile.exe')]:
        run(label,exe,['prepare','300'])
    for label,exe in [('pipeline-before',root+'/combat/dist/Flighting.Headless.exe'),
                      ('pipeline-direct',probe+'/VertexCandidate.exe'),('pipeline-after',root+'/combat/dist/Flighting.Headless.exe')]:
        subprocess.check_call(['python',probe+'/profile_pipeline.py',label],env=dict(env,FLIGHTING_PROFILE_EXE=exe))
finally:
    subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=hashes():raise RuntimeError('Production sources or binaries changed')
result=dict(production_unchanged=True,not_displayed_fps=True,hashes=before,
            runs=[json.load(open(folder+'/'+name+'-pipeline.json'))['summary'] for name in ('pipeline-before','pipeline-direct','pipeline-after')])
with open(folder+'/summary.json','w') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
