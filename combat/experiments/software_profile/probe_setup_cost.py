"""Compare identical prepared scenes using real writes or a RAM-only setup sink.

RAM-only is a diagnostic: it intentionally does not draw the game and its
throughput must never be reported as GPU/game FPS. Run through run_setup_probe.
"""
from __future__ import print_function
import ctypes as C,glob,hashlib,json,os,struct,sys,time

def median(values):
    values=sorted(values);n=len(values)
    return values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2.

library=os.path.abspath(sys.argv[1]);label=sys.argv[2];folder='/root/hackrpi/build/software-profile'
path='/dev/shm/hackrpi-setup-probe.bin'
os.environ['FLIGHTING_FRAME_FILE']=path
os.environ['SPINAL_WBUFFER']='1';os.environ['SPINAL_CACHE_COLORS']='1';os.environ['SPINAL_COVERAGE_REJECT']='1'
lib=C.CDLL(library)
signatures={
 'fg_open':([C.c_int,C.c_int],C.c_int),
 'fg_upload':([C.c_int,C.c_int,C.c_int,C.c_void_p],C.c_int),
 'fg_prepared_create':([],C.c_void_p),
 'fg_prepared_reset':([C.c_void_p,C.c_uint32],None),
 'fg_prepared_free':([C.c_void_p],None),
 'fg_prepared_add':([C.c_void_p,C.c_void_p,C.c_int,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int],C.c_int),
 'fg_pipeline_start':([],C.c_int),'fg_pipeline_wait':([],C.c_int),
 'fg_pipeline_submit':([C.c_void_p,C.c_double,C.c_double],C.c_int),
 'fg_pipeline_stop':([],C.c_int),'fg_close':([],None)}
for name,(arguments,result) in signatures.items():
 fn=getattr(lib,name);fn.argtypes=arguments;fn.restype=result

def check(result):
    if result:raise RuntimeError('Native result %d'%result)

def read_frame():
    with open(path,'rb') as f:
        magic,width,height,size,pixels=struct.unpack('<4sIIII',f.read(20))
        if (magic,width,height,pixels)!=(b'SFG1',320,240,153600):raise RuntimeError('Invalid frame')
        metadata=json.loads(f.read(size));data=f.read(pixels)
    return metadata,data

def read_scene(path):
    with open(path,'rb') as f:
        if f.read(4)!=b'RPL1':raise RuntimeError('Invalid RPL1')
        width,height,clear,nt,nd=struct.unpack('<iiiii',f.read(20))
        if (width,height)!=(320,240):raise RuntimeError('Wrong resolution')
        for unused in range(nt):
            identity,w,h=struct.unpack('<iii',f.read(12));pixels=C.create_string_buffer(f.read(w*h*4))
            check(lib.fg_upload(identity,w,h,pixels))
        handle=lib.fg_prepared_create()
        if not handle:raise MemoryError('Prepared frame')
        try:
            lib.fg_prepared_reset(handle,clear&0xffffffff)
            for unused in range(nd):
                nv,ni,texture,depth,cull=struct.unpack('<iiiii',f.read(20))
                vertices=C.create_string_buffer(f.read(nv*36));indices=C.create_string_buffer(f.read(ni*4))
                check(lib.fg_prepared_add(handle,vertices,nv,indices,ni,texture,depth,cull))
            if f.read(1):raise RuntimeError('Trailing RPL1 data')
        except:
            lib.fg_prepared_free(handle);raise
    return handle

opened=active=False;results=[]
try:
    check(lib.fg_open(320,240));opened=True
    check(lib.fg_pipeline_start());active=True
    scenes=sorted(glob.glob(folder+'/samples/*.rpl'))
    if len(scenes)!=7:raise RuntimeError('Expected seven original-profile checkpoints')
    for scene in scenes:
        handle=read_scene(scene);observations=[];hashes=[]
        try:
            for frame in range(18):
                start=time.time()
                check(lib.fg_pipeline_submit(handle,0,0))
                elapsed=(time.time()-start)*1000
                check(lib.fg_pipeline_wait());metadata,pixels=read_frame()
                if frame>=3:
                    # Read the C-to-C clock measurement. This board's Python
                    # ctypes double-return ABI reported constant zero.
                    observations.append(dict(submit_wall_ms=elapsed,submit_thread_cpu_ms=metadata['owner_cpu_ms'],
                        command_ms=metadata['command_submit_ms'],gpu_busy_ms=metadata['pipeline_busy_cycles']/50000.,
                        triangles=metadata['triangles_submitted']))
                    if 'probe_triangle_commands' in metadata:observations[-1]['actual_triangle_commands']=metadata['probe_triangle_commands']
                    if 'ram-only' not in label:hashes.append(hashlib.sha256(pixels).hexdigest())
            result=dict(scene=os.path.basename(scene),frames=len(observations),observations=observations,
                        median={key:median([row[key] for row in observations]) for key in observations[0]},pixel_hashes=sorted(set(hashes)))
            results.append(result);print(json.dumps(dict(label=label,scene=result['scene'],median=result['median'])));sys.stdout.flush()
        finally:lib.fg_prepared_free(handle)
finally:
    if active:check(lib.fg_pipeline_stop())
    if opened:lib.fg_close()
with open(folder+'/'+label+'-setup-cost.json','w') as f:json.dump(dict(label=label,diagnostic_not_rendering='ram-only' in label,scenes=results),f,indent=2)
