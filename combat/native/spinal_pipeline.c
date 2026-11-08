/* ABI1 remains available for serialized captures and rollback. The additional
 * pipeline API separates CPU-only preparation from the GPU owner thread.
 * Completed color buffers have explicit ownership until readback finishes. */
#define _GNU_SOURCE
#include "spinal_bridge.c"
#include <pthread.h>
#include <sched.h>

typedef struct {GrVertex *v;unsigned count,capacity;int texture,depth;} PipeDraw;
typedef struct {FgVertex vertex;GrVertex projected;double x,y;unsigned code;} PipeInput;
typedef struct {uint32_t clear;PipeDraw *draws;unsigned count,capacity,triangles,clipped,culled;PipeInput *input;unsigned input_capacity;} PipeFrame;
typedef struct {int occupied,ready;uint32_t offset,index;char metadata[3072];int meta_size;double started,render_seconds,prepared_ms,command_ms,drain_ms,slot_wait_ms,owner_cpu_ms,previous_publish_ms,ready_wait_ms,scene_wait_ms,geometry_cpu_ms,prepare_cpu_ms,previous_submit_ms;unsigned char pixels[BYTES];} PipeSlot;
static struct {
    int active,done,error,phase,reader_started,reader_policy,reader_policy_error;unsigned next,latest;uint32_t offset;
    volatile uint32_t *ddr;pthread_t reader;pthread_mutex_t mutex;pthread_cond_t changed;
    PipeSlot slots[2];unsigned char last_pixels[BYTES];int have_last;
    double last_publish_ms;
} pipe_state;
static int pipe_sync_count=3;
int flighting_flat_colors;
unsigned flighting_color_epoch;
static int pipe_cached_colors;
static int pipe_readback_batch;
static int pipe_coverage_reject;
static double current_ready_wait,current_scene_wait,current_geometry_cpu,current_prepare_cpu,previous_submit;
FG_EXPORT double fg_thread_cpu_ms(void){struct timespec t;if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t))return -1;return t.tv_sec*1000.0+t.tv_nsec/1e6;}
FG_EXPORT void fg_set_pipeline_waits(double ready,double scene,double geometry_cpu,double prepare_cpu,double previous){current_ready_wait=ready;current_scene_wait=scene;current_geometry_cpu=geometry_cpu;current_prepare_cpu=prepare_cpu;previous_submit=previous;}
static int pipe_finite(float value){uint32_t bits;memcpy(&bits,&value,sizeof(bits));return (bits&0x7f800000u)!=0x7f800000u;}
extern void __real_grSstIdle(void);
extern void __real_grDrawTriangle(const GrVertex *,const GrVertex *,const GrVertex *);
void __wrap_grSstIdle(void){
    if(pipe_state.phase)gpu_mmio_write32(sst,4096,0x120,0);else __real_grSstIdle();
}
void __wrap_grDrawTriangle(const GrVertex *a,const GrVertex *b,const GrVertex *c){
    int flat=a->r==b->r&&b->r==c->r&&a->g==b->g&&b->g==c->g&&a->b==b->b&&b->b==c->b;
    flighting_flat_colors=pipe_state.phase&&pipe_cached_colors&&flat;
    if(!flighting_flat_colors)flighting_color_epoch++;
    __real_grDrawTriangle(a,b,c);
    flighting_flat_colors=0;
    if(pipe_state.phase){int n;for(n=0;n<pipe_sync_count;n++)gpu_mmio_write32(sst,4096,0x120,0);}
}
static int pipe_clip(const FgVertex *input,FgVertex *output){
    int all=127,any=0,i,p;
    for(i=0;i<3;i++){int code=0;for(p=0;p<7;p++)if(fg_plane(input+i,p)<0)code|=1<<p;all&=code;any|=code;}
    if(all)return 0;if(!any){memcpy(output,input,3*sizeof(*input));return 3;}
    return fg_clip_triangle(input,output);
}
FG_EXPORT void *fg_prepared_create(void){return calloc(1,sizeof(PipeFrame));}
FG_EXPORT void fg_prepared_reset(void *handle,uint32_t clear){PipeFrame *f=handle;if(f){f->clear=clear;f->count=f->triangles=f->clipped=f->culled=0;}}
FG_EXPORT void fg_prepared_free(void *handle){PipeFrame *f=handle;unsigned i;if(!f)return;for(i=0;i<f->capacity;i++)free(f->draws[i].v);free(f->input);free(f->draws);free(f);}
static double pipe_clamp(double value,double maximum){return value<=0?0:value>=maximum?maximum:value==value?value:maximum;}
static GrVertex pipe_project(const FgVertex *input,int texture){
    const double *p=input->v;GrVertex v;double inverse=1/p[3],depth=(1-(p[2]*inverse*.5+.5))*65535;
    memset(&v,0,sizeof(v));v.x=(float)((p[0]*inverse*.5+.5)*width);v.y=(float)((.5-p[1]*inverse*.5)*height);
    v.ooz=(float)pipe_clamp(depth,65535);v.oow=(float)(inverse*.19);v.a=255;
    v.r=(float)pipe_clamp(p[4]*255,255);v.g=(float)pipe_clamp(p[5]*255,255);v.b=(float)pipe_clamp(p[6]*255,255);v.tmuvtx[0].oow=v.oow;
    if(texture){v.tmuvtx[0].sow=(float)(pipe_clamp(p[7],1)*255*v.oow);v.tmuvtx[0].tow=(float)((1-pipe_clamp(p[8],1))*255*v.oow);}
    return v;
}
static int pipe_reserve(PipeDraw *d,unsigned additional){
    if(d->count+additional>d->capacity){unsigned capacity=d->capacity?d->capacity*2:512;GrVertex *vertices;while(capacity<d->count+additional)capacity*=2;vertices=realloc(d->v,capacity*sizeof(*vertices));if(!vertices)return -5;d->v=vertices;d->capacity=capacity;}
    return 0;
}
/* Conservative geometry rejection, not a replacement rasterizer. The accepted
 * core uses 12.4 vertex coordinates. Check a superset of its pixel positions
 * (both integer and half-integer centers), including every edge. Only tiny
 * triangles with no possible covered sample are removed. */
static int pipe_no_coverage(const GrVertex *a,const GrVertex *b,const GrVertex *c){
    int ax,ay,bx,by,cx,cy,minx,maxx,miny,maxy,x,y,startx,starty,area;
    if(!pipe_coverage_reject)return 0;
    ax=(int)(a->x*16);ay=(int)(a->y*16);bx=(int)(b->x*16);by=(int)(b->y*16);cx=(int)(c->x*16);cy=(int)(c->y*16);
    if(ax<0||ay<0||bx<0||by<0||cx<0||cy<0||ax>W*16||bx>W*16||cx>W*16||ay>H*16||by>H*16||cy>H*16)return 0;
    minx=ax<bx?ax:bx;if(cx<minx)minx=cx;maxx=ax>bx?ax:bx;if(cx>maxx)maxx=cx;
    miny=ay<by?ay:by;if(cy<miny)miny=cy;maxy=ay>by?ay:by;if(cy>maxy)maxy=cy;
    startx=(minx+7)&~7;starty=(miny+7)&~7;
    if(startx>maxx||starty>maxy)return 1;
    if(maxx-minx>32||maxy-miny>32)return 0;
    area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax);if(!area)return 0;
    for(y=starty;y<=maxy;y+=8)for(x=startx;x<=maxx;x+=8){
        int ab=(bx-ax)*(y-ay)-(by-ay)*(x-ax),bc=(cx-bx)*(y-by)-(cy-by)*(x-bx),ca=(ax-cx)*(y-cy)-(ay-cy)*(x-cx);
        if((ab>=0&&bc>=0&&ca>=0)||(ab<=0&&bc<=0&&ca<=0))return 0;
    }
    return 1;
}
static int pipe_prepare_add(void *handle,const void *vertices,int nv,const int32_t *ix,int ni,int texture,int depth,int cull,int host_vertices){
    PipeFrame *f=handle;PipeDraw *d;int i,j,k,n;
    const float *v=vertices;const double *host=vertices;
    if(!f||(!vertices&&nv)||(!ix&&ni)||nv<0||nv>750000||ni<0||ni>750000||ni%3||f->count>=4096||texture<0||texture>=MAX_TEX)return -1;
    for(i=0;i<ni;i++)if(ix[i]<0||ix[i]>=nv)return -1;
    if(f->count==f->capacity){unsigned old=f->capacity,new_capacity=old?old*2:16;PipeDraw *draws=realloc(f->draws,new_capacity*sizeof(*draws));if(!draws)return -5;f->draws=draws;memset(draws+old,0,(new_capacity-old)*sizeof(*draws));f->capacity=new_capacity;}
    d=f->draws+f->count;d->count=0;d->texture=texture;d->depth=depth;
    if((unsigned)nv>f->input_capacity){PipeInput *input=realloc(f->input,(size_t)nv*sizeof(*input));if(!input)return -5;f->input=input;f->input_capacity=(unsigned)nv;}
    for(i=0;i<nv;i++){
        PipeInput *input=f->input+i;input->code=0;
        for(k=0;k<9;k++){float value=host_vertices?(float)host[i*9+k]:v[i*9+k];if(!pipe_finite(value))return -1;input->vertex.v[k]=value;}
        {const double *p=input->vertex.v;double w=p[3];
            if(w-1e-7<0)input->code|=1;if(w+p[0]<0)input->code|=2;if(w-p[0]<0)input->code|=4;
            if(w+p[1]<0)input->code|=8;if(w-p[1]<0)input->code|=16;if(w+p[2]<0)input->code|=32;if(w-p[2]<0)input->code|=64;
        }
        if(!input->code){input->x=input->vertex.v[0]/input->vertex.v[3];input->y=input->vertex.v[1]/input->vertex.v[3];input->projected=pipe_project(&input->vertex,texture);}
    }
    for(i=0;i<ni;i+=3){
        FgVertex triangle[3],polygon[16];
        PipeInput *a=f->input+ix[i],*b=f->input+ix[i+1],*c=f->input+ix[i+2];
        if(a->code&b->code&c->code){f->culled++;continue;}
        if(!(a->code|b->code|c->code)){
            double area=(b->x-a->x)*(c->y-a->y)-(b->y-a->y)*(c->x-a->x);
            if(fabs(area)<1e-12||(cull&&area<=0)){f->culled++;continue;}
            if(pipe_no_coverage(&a->projected,&b->projected,&c->projected)){f->culled++;continue;}
            if(pipe_reserve(d,3))return -5;
            d->v[d->count++]=a->projected;d->v[d->count++]=b->projected;d->v[d->count++]=c->projected;f->triangles++;continue;
        }
        triangle[0]=a->vertex;triangle[1]=b->vertex;triangle[2]=c->vertex;
        n=pipe_clip(triangle,polygon);if(n<0)return -3;if(n<3){f->culled++;continue;}if(n!=3)f->clipped++;
        for(j=1;j+1<n;j++){
            FgVertex *p[3]={polygon,polygon+j,polygon+j+1};double area=fg_screen_area(p[0],p[1],p[2]);
            if(fabs(area)<1e-12||(cull&&area<=0)){f->culled++;continue;}
            {GrVertex projected[3];for(k=0;k<3;k++)projected[k]=pipe_project(p[k],texture);
             if(pipe_no_coverage(projected,projected+1,projected+2)){f->culled++;continue;}
             if(pipe_reserve(d,3))return -5;for(k=0;k<3;k++)d->v[d->count++]=projected[k];}
            f->triangles++;
        }
    }
    f->count++;return 0;
}
FG_EXPORT int fg_prepared_add(void *handle,const float *v,int nv,const int32_t *ix,int ni,int texture,int depth,int cull){return pipe_prepare_add(handle,v,nv,ix,ni,texture,depth,cull,0);}
FG_EXPORT int fg_prepared_add_vertices(void *handle,const FgVertex *v,int nv,const int32_t *ix,int ni,int texture,int depth,int cull){return pipe_prepare_add(handle,v,nv,ix,ni,texture,depth,cull,1);}
static void pipe_draw_state(PipeDraw *d){
    TextureSlot *t;flighting_color_epoch++;grSstIdle();
    /* Bypass auxiliary-plane reads for draws that do not use depth. */
    grDepthBufferMode(d->depth?(wbuffer?GR_DEPTHBUFFER_WBUFFER:GR_DEPTHBUFFER_ZBUFFER):GR_DEPTHBUFFER_DISABLE);
    grDepthBufferFunction(d->depth?(wbuffer?GR_CMP_LEQUAL:GR_CMP_GREATER):GR_CMP_ALWAYS);grDepthMask(d->depth?FXTRUE:FXFALSE);
    if(d->texture){
        t=&textures[d->texture];grTexSource(GR_TMU0,t->address,GR_MIPMAPLEVELMASK_BOTH,&t->info);
        grTexClampMode(GR_TMU0,GR_TEXTURECLAMP_CLAMP,GR_TEXTURECLAMP_CLAMP);grTexFilterMode(GR_TMU0,GR_TEXTUREFILTER_POINT_SAMPLED,GR_TEXTUREFILTER_POINT_SAMPLED);
        grTexMipMapMode(GR_TMU0,GR_MIPMAP_DISABLE,FXFALSE);grTexCombine(GR_TMU0,GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,FXFALSE,FXFALSE);
        grColorCombine(GR_COMBINE_FUNCTION_SCALE_OTHER,GR_COMBINE_FACTOR_LOCAL,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_TEXTURE,FXFALSE);
    }else grColorCombine(GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_NONE,FXFALSE);
}
static int pipe_publish(PipeSlot *slot,double copy,double capture){
    const char *path=getenv("FLIGHTING_FRAME_FILE");char temporary[1024],meta[4096];uint32_t header[5];int fd,n,failed;
    if(!path||!*path)return 0;
    n=snprintf(meta,sizeof(meta),"%.*s,\"copy_seconds\":%.9f,\"capture_seconds\":%.9f,\"prepare_ms\":%.3f,\"command_submit_ms\":%.3f,\"drain_ms\":%.3f,\"slot_wait_ms\":%.3f,\"owner_cpu_ms\":%.3f,\"previous_publish_ms\":%.3f,\"ready_wait_ms\":%.3f,\"scene_wait_ms\":%.3f,\"geometry_cpu_ms\":%.3f,\"prepare_cpu_ms\":%.3f,\"previous_submit_ms\":%.3f,\"readback_overlap\":true}",slot->meta_size-1,slot->metadata,copy,capture,slot->prepared_ms,slot->command_ms,slot->drain_ms,slot->slot_wait_ms,slot->owner_cpu_ms,slot->previous_publish_ms,slot->ready_wait_ms,slot->scene_wait_ms,slot->geometry_cpu_ms,slot->prepare_cpu_ms,slot->previous_submit_ms);
    if(n<0||n>=(int)sizeof(meta)||snprintf(temporary,sizeof(temporary),"%s.next",path)>=(int)sizeof(temporary))return -3;
    memcpy(header,"SFG1",4);header[1]=W;header[2]=H;header[3]=n;header[4]=BYTES;
    fd=open(temporary,O_WRONLY|O_CREAT|O_TRUNC,0600);if(fd<0)return -3;
    failed=write_all(fd,header,sizeof(header))||write_all(fd,meta,n)||write_all(fd,slot->pixels,BYTES)||fsync(fd);if(close(fd))failed=1;
    return failed||rename(temporary,path)?-3:0;
}
static void *pipe_copy(void *unused){
    unsigned x,y;int chosen;(void)unused;
    {
        int policy,error=0;struct sched_param parameters={0};
        if(pipe_readback_batch&&sched_setscheduler(0,SCHED_BATCH,&parameters))error=errno;
        policy=sched_getscheduler(0);if(policy<0&&!error)error=errno;
        pthread_mutex_lock(&pipe_state.mutex);
        pipe_state.reader_policy=policy;pipe_state.reader_policy_error=error;pipe_state.reader_started=1;
        pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);
    }
    for(;;){PipeSlot *slot;double start,copy;int result;
        pthread_mutex_lock(&pipe_state.mutex);
        while(!pipe_state.slots[0].ready&&!pipe_state.slots[1].ready&&!pipe_state.done)pthread_cond_wait(&pipe_state.changed,&pipe_state.mutex);
        if(!pipe_state.slots[0].ready&&!pipe_state.slots[1].ready&&pipe_state.done){pthread_mutex_unlock(&pipe_state.mutex);break;}
        chosen=pipe_state.slots[0].ready?0:1;if(pipe_state.slots[0].ready&&pipe_state.slots[1].ready&&pipe_state.slots[1].index<pipe_state.slots[0].index)chosen=1;slot=pipe_state.slots+chosen;slot->ready=0;pthread_mutex_unlock(&pipe_state.mutex);
        start=seconds();__asm__ __volatile__("dmb sy" ::: "memory");
        for(y=0;y<H;y++)for(x=0;x<W/2;x++){
            uint32_t word=pipe_state.ddr[slot->offset/4+y*W/2+x];unsigned at=y*W*2+x*4;
            memcpy(slot->pixels+at,&word,sizeof(word));
        }
        __asm__ __volatile__("dmb sy" ::: "memory");copy=seconds()-start;
        start=seconds();result=pipe_publish(slot,copy,seconds()-slot->started);
        pthread_mutex_lock(&pipe_state.mutex);
        if(result)pipe_state.error=result;
        memcpy(pipe_state.last_pixels,slot->pixels,BYTES);pipe_state.have_last=1;pipe_state.latest++;
        pipe_state.last_publish_ms=(seconds()-start)*1000;
        slot->occupied=0;pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);
    }
    return NULL;
}
FG_EXPORT int fg_pipeline_start(void){
    uint32_t stride,display;
    if(!opened||in_frame||pipe_state.active||rd(control,8)!=0)return -4;
    pipe_sync_count=getenv("SPINAL_PIPELINE_SYNCS")?atoi(getenv("SPINAL_PIPELINE_SYNCS")):3;if(pipe_sync_count<2||pipe_sync_count>8)return -1;
    pipe_cached_colors=getenv("SPINAL_CACHE_COLORS")&&strcmp(getenv("SPINAL_CACHE_COLORS"),"1")==0;
    pipe_readback_batch=getenv("SPINAL_READBACK_BATCH")&&strcmp(getenv("SPINAL_READBACK_BATCH"),"1")==0;
    pipe_coverage_reject=getenv("SPINAL_COVERAGE_REJECT")&&strcmp(getenv("SPINAL_COVERAGE_REJECT"),"1")==0;
    stride=((rd(sst,0x214)>>4)&15)*64;display=(rd(sst,0)>>10)&1;
    memset(&pipe_state,0,sizeof(pipe_state));pipe_state.offset=((rd(sst,0x218)>>11)&511)*4096;
    if(stride!=W||display||!pipe_state.offset||pipe_state.offset+BYTES>4*1024*1024)return -3;
    pipe_state.ddr=mmap(NULL,4*1024*1024,PROT_READ,MAP_SHARED,mem_fd,0x3f400000ULL);if(pipe_state.ddr==MAP_FAILED)return -4;
    pthread_mutex_init(&pipe_state.mutex,NULL);pthread_cond_init(&pipe_state.changed,NULL);
    if(pthread_create(&pipe_state.reader,NULL,pipe_copy,NULL)){munmap((void *)pipe_state.ddr,4*1024*1024);pthread_mutex_destroy(&pipe_state.mutex);pthread_cond_destroy(&pipe_state.changed);return -4;}
    pthread_mutex_lock(&pipe_state.mutex);while(!pipe_state.reader_started)pthread_cond_wait(&pipe_state.changed,&pipe_state.mutex);pthread_mutex_unlock(&pipe_state.mutex);
    pipe_state.active=1;return 0;
}
FG_EXPORT int fg_pipeline_wait(void){int error;if(!pipe_state.active)return -4;pthread_mutex_lock(&pipe_state.mutex);while((pipe_state.slots[0].occupied||pipe_state.slots[1].occupied)&&!pipe_state.error)pthread_cond_wait(&pipe_state.changed,&pipe_state.mutex);error=pipe_state.error;pthread_mutex_unlock(&pipe_state.mutex);return error;}
FG_EXPORT int fg_pipeline_read_last(uint8_t *rgb,int length){if(!pipe_state.active||!rgb||length!=BYTES)return -1;pthread_mutex_lock(&pipe_state.mutex);if(!pipe_state.have_last){pthread_mutex_unlock(&pipe_state.mutex);return -4;}memcpy(rgb,pipe_state.last_pixels,BYTES);pthread_mutex_unlock(&pipe_state.mutex);return 0;}
FG_EXPORT int fg_pipeline_stop(void){int error;if(!pipe_state.active)return 0;fg_pipeline_wait();pthread_mutex_lock(&pipe_state.mutex);pipe_state.done=1;pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);pthread_join(pipe_state.reader,NULL);error=pipe_state.error;munmap((void *)pipe_state.ddr,4*1024*1024);pthread_mutex_destroy(&pipe_state.mutex);pthread_cond_destroy(&pipe_state.changed);pipe_state.active=pipe_state.phase=0;return error;}
static int pipe_snapshot_metadata(PipeSlot *slot);
FG_EXPORT int fg_pipeline_submit(void *handle,double geometry,double prepared){
    PipeFrame *f=handle;PipeSlot *slot;unsigned d,i,number;double start,wait_start=seconds(),cpu_start=fg_thread_cpu_ms();int failed=0;
    if(!pipe_state.active||!f||in_frame)return -4;
    for(d=0;d<f->count;d++)if(f->draws[d].texture&&!textures[f->draws[d].texture].valid)return -1;
    number=pipe_state.next&1;slot=pipe_state.slots+number;
    pthread_mutex_lock(&pipe_state.mutex);while(slot->occupied&&!pipe_state.error)pthread_cond_wait(&pipe_state.changed,&pipe_state.mutex);
    if(pipe_state.error){int error=pipe_state.error;pthread_mutex_unlock(&pipe_state.mutex);return error;}slot->occupied=1;slot->previous_publish_ms=pipe_state.last_publish_ms;pthread_mutex_unlock(&pipe_state.mutex);
    start=seconds();slot->started=start;slot->offset=number*pipe_state.offset;slot->index=pipe_state.next;
    slot->slot_wait_ms=(start-wait_start)*1000;slot->ready_wait_ms=current_ready_wait;slot->scene_wait_ms=current_scene_wait;slot->geometry_cpu_ms=current_geometry_cpu;slot->prepare_cpu_ms=current_prepare_cpu;slot->previous_submit_ms=previous_submit;
    if(rd(control,8)!=0||log_start()){failed=-3;goto fail;}
    pipe_state.phase=1;in_frame=1;if(wr(12,4)){failed=-3;goto fail;}
    configure();grRenderBuffer(number?GR_BUFFER_BACKBUFFER:GR_BUFFER_FRONTBUFFER);grBufferClear(abgr(f->clear),0,wbuffer?GR_WDEPTHVALUE_FARTHEST:0);
    for(d=0;d<f->count;d++){PipeDraw *draw=f->draws+d;if(!draw->count)continue;pipe_draw_state(draw);for(i=0;i<draw->count;i+=3)grDrawTriangle(draw->v+i,draw->v+i+1,draw->v+i+2);grSstIdle();}
    slot->command_ms=(seconds()-start)*1000;
    pipe_state.phase=0;grSstIdle();
    {uint32_t state;double fence_start;if(wr(12,1)){failed=-3;goto fail;}fence_start=seconds();do{state=rd(control,8);if(state&8u||seconds()-fence_start>3){failed=-3;goto fail;}}while(!(state&4u));}
    if(rd(sst,0x254)&7u){failed=-3;goto fail;}
    gpu_sequence=rd(control,0x20);render_cycles=rd(control,0x24);busy_cycles=rd(control,0x2c);
    submitted=f->triangles;clipped=f->clipped;culled=f->culled;sequence++;geometry_ms=geometry;host_submit_ms=(seconds()-start)*1000;slot->prepared_ms=prepared;
    slot->drain_ms=host_submit_ms-slot->command_ms;
    slot->owner_cpu_ms=fg_thread_cpu_ms()-cpu_start;
    if(pipe_snapshot_metadata(slot)){failed=-3;goto fail;}
    if(wr(12,2)||rd(control,8)!=0){failed=-3;goto fail;}in_frame=0;log_end();
    pthread_mutex_lock(&pipe_state.mutex);slot->ready=1;pipe_state.next++;pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);return 0;
fail:
    pipe_state.phase=0;if(rd(control,8)&4u)wr(12,2);in_frame=0;log_end();pthread_mutex_lock(&pipe_state.mutex);slot->occupied=0;pipe_state.error=failed;pthread_cond_broadcast(&pipe_state.changed);pthread_mutex_unlock(&pipe_state.mutex);return failed;
}

static int pipe_snapshot_metadata(PipeSlot *slot){
    slot->meta_size=snprintf(slot->metadata,sizeof(slot->metadata),"{\"source\":\"hardware\",\"renderer\":\"SpinalVoodoo\",\"scene\":\"combat\",\"gpu_id\":1196447026,\"abi\":2,\"frame_sequence\":%u,\"gpu_sequence\":%u,\"render_cycles\":%u,\"clock_hz\":%u,\"pipeline_busy_cycles\":%u,\"submission_mode\":\"%s\",\"triangles_submitted\":%u,\"triangles_clipped\":%u,\"triangles_culled\":%u,\"tick\":%lld,\"health\":%d,\"kills\":%d,\"distance\":%.3f,\"paused\":%s,\"game_over\":%s,\"simulation_target_hz\":60,\"sensor_fresh\":%s,\"sensor_ready\":%s,\"sensor_calibrating\":%s,\"sensor_samples\":%lld,\"sensor_roll\":%.2f,\"sensor_pitch\":%.2f,\"geometry_ms\":%.3f,\"host_submit_ms\":%.3f,\"queued_syncs\":%d}",sequence,gpu_sequence,render_cycles,clock_hz,busy_cycles,"queued-sync",submitted,clipped,culled,game_tick,health,kills,distance,paused?"true":"false",game_over?"true":"false",sensor_fresh?"true":"false",sensor_ready?"true":"false",sensor_calibrating?"true":"false",sensor_samples,sensor_roll,sensor_pitch,geometry_ms,host_submit_ms,pipe_sync_count);
    if(slot->meta_size<1||slot->meta_size>=(int)sizeof(slot->metadata))return -3;
    {int at=slot->meta_size-1,remaining=(int)sizeof(slot->metadata)-at;
     int n=snprintf(slot->metadata+at,remaining,",\"readback_policy\":%d,\"readback_policy_error\":%d}",pipe_state.reader_policy,pipe_state.reader_policy_error);
     if(n<0||n>=remaining)return -3;slot->meta_size=at+n;}
    return 0;
}
