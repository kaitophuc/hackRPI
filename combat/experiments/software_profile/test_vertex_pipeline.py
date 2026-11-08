"""Gate direct vertex storage, then compare preparation and full moving FPS."""
from __future__ import print_function
import glob,hashlib,json,os,subprocess
from urllib2 import urlopen

os.chdir('/root/hackrpi');folder='build/software-profile';probe='/dev/shm/hackrpi-vertex-candidate'
response=urlopen('http://127.0.0.1:8081/metrics',timeout=3);status=json.load(response);response.close()
if not status.get('simulation_paused',True) or any(c.get('kind')=='browser' and c.get('visible') for c in status.get('display_clients',[])):
    raise RuntimeError('A visible or active browser is using the game; leave it running')
paths=['combat/dist/Flighting.Headless.exe','combat/dist/libflighting_spinal_bridge.so','combat/native/spinal_pipeline.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes();env=dict(os.environ,MONO_CFG_DIR='/root/hackrpi/runtime/etc',MONO_PATH='/root/hackrpi/runtime/usr/lib/mono/4.5',
                       LD_LIBRARY_PATH='/root/hackrpi/combat/dist',SPINAL_WBUFFER='1',FLIGHTING_PACKED_REUSE='1',
                       SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',FLIGHTING_CITY_XY_CACHE='1',
                       SPINAL_READBACK_BATCH='1',FLIGHTING_DIRECT_VERTEX_BUFFER='1',FLIGHTING_PROFILE_TICKS='1200')
for manifest_path,directory,count in [(folder+'/compiler-cross-reference.json','/dev/shm/hackrpi-compiler-reference',22),
                                      (folder+'/depth-mode-validation.json','/dev/shm/hackrpi-depth-mode-reference',6)]:
    manifest=json.load(open(manifest_path))
    if not manifest.get('passed') or len(manifest['reference_hashes'])!=count:raise RuntimeError('Incomplete pixel references')
    for name,digest in manifest['reference_hashes'].items():
        if hashlib.sha256(open(directory+'/'+name,'rb').read()).hexdigest()!=digest:raise RuntimeError('Pixel reference changed')
def run(label,exe,args,extra=None):
    with open(folder+'/'+label+'.log','w') as log:
        subprocess.check_call(['runtime/usr/bin/mono-sgen',exe]+args,env=dict(env,**(extra or {})),stdout=log,stderr=log)
    print(label+' passed')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    samples=sorted(glob.glob(folder+'/samples/*.rpl'))+sorted(glob.glob('build/batching/diagnostic-scene-*.rpl'))
    if len(samples)!=14:raise RuntimeError('Expected fourteen saved scenes')
    run('vertex-direct-pixels',probe+'/VertexPixels.exe',samples,dict(FLIGHTING_VALIDATION_BASELINE_DIR='/dev/shm/hackrpi-compiler-reference',FLIGHTING_VALIDATION_REQUIRE_BASELINE='1'))
    run('vertex-direct-depth-modes',probe+'/VertexDepthModes.exe',['verify','/dev/shm/hackrpi-depth-mode-reference'])
    for label,exe in [('vertex-prepare-before',folder+'/BeforeVertexProfile.exe'),('vertex-prepare-direct',probe+'/VertexProfile.exe'),('vertex-prepare-after',folder+'/BeforeVertexProfile.exe')]:
        run(label,exe,['prepare','300'])
    for label,exe in [('vertex-pipeline-before','/root/hackrpi/combat/dist/Flighting.Headless.exe'),
                       ('vertex-pipeline-direct',probe+'/VertexCandidate.exe'),
                       ('vertex-pipeline-after','/root/hackrpi/combat/dist/Flighting.Headless.exe')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],env=dict(env,FLIGHTING_PROFILE_EXE=exe))
finally:
    after=hashes();subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=after:raise RuntimeError('Production sources or binaries changed')
print(json.dumps(dict(production_unchanged=True,hashes=after)))
