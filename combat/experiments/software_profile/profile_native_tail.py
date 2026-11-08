"""Instrument post-render bookkeeping in a separate library and executable copy."""
from __future__ import print_function
import hashlib,json,os,shutil,subprocess
os.chdir('/root/hackrpi');folder='build/software-profile';probe=folder+'/tail-probe'
if not os.path.isdir(probe):os.mkdir(probe)
paths=['combat/dist/Flighting.Headless.exe','combat/dist/libflighting_spinal_bridge.so','combat/native/spinal_pipeline.c','combat/native/spinal_color_cache.c']
def hashes():return {p:hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
before=hashes();input_path=folder+'/tail-probe-input.c'
original=open(input_path,'rb').read()
if hashlib.sha256(original).hexdigest()!='f54b21a70d5f60a47be24c7c335365570eba508154dd9189e717379fcedd7a0f':
    raise RuntimeError('Tail diagnostic requires the pinned pre-policy native source')
source=original.replace('\r\n','\n')
def change(old,new):
    global source
    if source.count(old)!=1:raise RuntimeError('Unexpected source marker: '+old[:70])
    source=source.replace(old,new)
change('#include "spinal_bridge.c"','#include "/root/hackrpi/combat/native/spinal_bridge.c"')
change('static int pipe_sync_count=3;','static int pipe_sync_count=3;\nstatic int probe_wake_after_unlock;\nstatic __thread int probe_notify_active;\nstatic int probe_copy_policy,probe_copy_policy_error;\nstatic double previous_lock_ms,previous_signal_ms,previous_unlock_ms;\nstatic double previous_metadata_ms,previous_release_ms,previous_log_ms,previous_notify_ms,previous_tail_ms;')
change('#include <pthread.h>','#include <pthread.h>\n#include <sched.h>\n#ifndef SCHED_BATCH\n#define SCHED_BATCH 3\n#endif')
change('FG_EXPORT double fg_thread_cpu_ms(void)', '''static int probe_lock(pthread_mutex_t *mutex){
    if(!probe_notify_active)return pthread_mutex_lock(mutex);
    double start=seconds();int result=pthread_mutex_lock(mutex);previous_lock_ms=(seconds()-start)*1000;return result;
}
static int probe_unlock(pthread_mutex_t *mutex){
    if(!probe_notify_active)return pthread_mutex_unlock(mutex);
    double start=seconds();int result=pthread_mutex_unlock(mutex);previous_unlock_ms=(seconds()-start)*1000;return result;
}
static int probe_broadcast(pthread_cond_t *condition){
    if(!probe_notify_active)return pthread_cond_broadcast(condition);
    double start=seconds();int result=pthread_cond_broadcast(condition);previous_signal_ms=(seconds()-start)*1000;return result;
}
#define pthread_mutex_lock probe_lock
#define pthread_mutex_unlock probe_unlock
#define pthread_cond_broadcast probe_broadcast
FG_EXPORT double fg_thread_cpu_ms(void)''')
change('    unsigned x,y;int chosen;(void)unused;', '''    unsigned x,y;int chosen;(void)unused;
    if(getenv("SPINAL_PROBE_COPY_BATCH")&&strcmp(getenv("SPINAL_PROBE_COPY_BATCH"),"1")==0){
        struct sched_param parameters={0};
        int error=sched_setscheduler(0,SCHED_BATCH,&parameters)?errno:0;
        __atomic_store_n(&probe_copy_policy_error,error,__ATOMIC_RELEASE);
    }
    __atomic_store_n(&probe_copy_policy,sched_getscheduler(0),__ATOMIC_RELEASE);''')
change('    pipe_coverage_reject=getenv("SPINAL_COVERAGE_REJECT")&&strcmp(getenv("SPINAL_COVERAGE_REJECT"),"1")==0;',
       '    pipe_coverage_reject=getenv("SPINAL_COVERAGE_REJECT")&&strcmp(getenv("SPINAL_COVERAGE_REJECT"),"1")==0;\n    probe_wake_after_unlock=getenv("SPINAL_PROBE_WAKE_AFTER_UNLOCK")&&strcmp(getenv("SPINAL_PROBE_WAKE_AFTER_UNLOCK"),"1")==0;')
change('double start,wait_start=seconds(),cpu_start=fg_thread_cpu_ms();','double tail_start,meta_end,release_end,logging_end,tail_end;double start,wait_start=seconds(),cpu_start=fg_thread_cpu_ms();')
change('    if(pipe_snapshot_metadata(slot)){failed=-3;goto fail;}','    tail_start=seconds();if(pipe_snapshot_metadata(slot)){failed=-3;goto fail;}meta_end=seconds();')
change('if(wr(12,2)||rd(control,8)!=0){failed=-3;goto fail;}in_frame=0;log_end();','if(wr(12,2)||rd(control,8)!=0){failed=-3;goto fail;}in_frame=0;release_end=seconds();log_end();logging_end=seconds();')
change('pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);return 0;\nfail:',
       'if(probe_wake_after_unlock){pthread_mutex_unlock(&pipe_state.mutex);pthread_cond_broadcast(&pipe_state.changed);}else{pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);}tail_end=seconds();previous_metadata_ms=(meta_end-tail_start)*1000;previous_release_ms=(release_end-meta_end)*1000;previous_log_ms=(logging_end-release_end)*1000;previous_notify_ms=(tail_end-logging_end)*1000;previous_tail_ms=(tail_end-tail_start)*1000;return 0;\nfail:')
change('pthread_mutex_lock(&pipe_state.mutex);slot->ready=1;pipe_state.next++;','probe_notify_active=1;pthread_mutex_lock(&pipe_state.mutex);slot->ready=1;pipe_state.next++;')
change('previous_tail_ms=(tail_end-tail_start)*1000;return 0;','previous_tail_ms=(tail_end-tail_start)*1000;probe_notify_active=0;return 0;')
timing_format=',"previous_metadata_ms":%.6f,"previous_release_ms":%.6f,"previous_log_ms":%.6f,"previous_notify_ms":%.6f,"previous_native_tail_ms":%.6f,"previous_notify_lock_ms":%.6f,"previous_notify_signal_ms":%.6f,"previous_notify_unlock_ms":%.6f,"readback_policy":%d,"readback_policy_error":%d}'
change('    return slot->meta_size<0||slot->meta_size>=(int)sizeof(slot->metadata)?-3:0;','''    if(slot->meta_size<1||slot->meta_size>=(int)sizeof(slot->metadata))return -3;
    {int at=slot->meta_size-1,remaining=(int)sizeof(slot->metadata)-at;
     int n=snprintf(slot->metadata+at,remaining,TIMING_FORMAT,previous_metadata_ms,previous_release_ms,previous_log_ms,previous_notify_ms,previous_tail_ms,previous_lock_ms,previous_signal_ms,previous_unlock_ms,__atomic_load_n(&probe_copy_policy,__ATOMIC_ACQUIRE),__atomic_load_n(&probe_copy_policy_error,__ATOMIC_ACQUIRE));
     if(n<0||n>=remaining)return -3;slot->meta_size=at+n;}return 0;'''.replace('TIMING_FORMAT',json.dumps(timing_format)))
with open(probe+'/spinal_tail.c','w') as f:f.write(source)
build=open('combat/board/build_native.sh').read().replace('root=$(CDPATH= cd -- "$here/../.." && pwd)','root=/root/hackrpi')
build=build.replace('$root/combat/native/spinal_pipeline.c','$root/'+probe+'/spinal_tail.c')
build=build.replace('$root/combat/dist/libflighting_spinal_bridge.so.next','$root/'+probe+'/libflighting_spinal_bridge.so')
build=build[:build.index('\nmv ')]+'\n'
process=subprocess.Popen(['sh','-s'],stdin=subprocess.PIPE);process.communicate(build.encode('ascii'))
if process.returncode:raise RuntimeError('Tail-probe build failed')
shutil.copyfile('combat/dist/Flighting.Headless.exe',probe+'/Flighting.Headless.exe')
subprocess.check_call(['python','combat/board/stop_service.py'])
try:
    for label,enabled in [('copy-policy-before','0'),('copy-policy-batch','1'),('copy-policy-after','0')]:
        subprocess.check_call(['python',folder+'/profile_pipeline.py',label],env=dict(os.environ,FLIGHTING_PROFILE_EXE='/root/hackrpi/'+probe+'/Flighting.Headless.exe',LD_LIBRARY_PATH='/root/hackrpi/'+probe,SPINAL_CACHE_COLORS='1',SPINAL_COVERAGE_REJECT='1',SPINAL_PROBE_WAKE_AFTER_UNLOCK='0',SPINAL_PROBE_COPY_BATCH=enabled))
finally:
    after=hashes();subprocess.check_call(['sh','combat/board/start_service.sh'])
    if before!=after:raise RuntimeError('Production sources or binaries changed')
print(json.dumps(dict(production_unchanged=True)))
