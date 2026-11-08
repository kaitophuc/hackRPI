/* Isolated throughput ceiling experiment: immutable prepared geometry,
 * actual GPU rendering, two owned color buffers and verified frame stamps.
 * Geometry preparation is separately timed, not claimed as live game FPS. */
#define main scalar_probe_main
#include "probe.c"
#undef main
#include <pthread.h>
typedef struct {GrVertex *vertices;unsigned count,capacity;ReplayDraw *source;} Prepared;
static Prepared *record_to;
static int prepared_serial;
static void record_triangle(const GrVertex *a,const GrVertex *b,const GrVertex *c){
    Prepared *p=record_to;
    if(p->count+3>p->capacity){p->capacity=p->capacity?p->capacity*2:512;p->vertices=realloc(p->vertices,p->capacity*sizeof(GrVertex));if(!p->vertices)exit(2);}
    p->vertices[p->count++]=*a;p->vertices[p->count++]=*b;p->vertices[p->count++]=*c;
}
static void state_for(ReplayDraw *r){
    TextureSlot *t;grDepthBufferFunction(r->depth?GR_CMP_LEQUAL:GR_CMP_ALWAYS);grDepthMask(r->depth?FXTRUE:FXFALSE);
    if(r->texture){
        t=&textures[r->texture];grTexSource(GR_TMU0,t->address,GR_MIPMAPLEVELMASK_BOTH,&t->info);
        grTexClampMode(GR_TMU0,GR_TEXTURECLAMP_CLAMP,GR_TEXTURECLAMP_CLAMP);grTexFilterMode(GR_TMU0,GR_TEXTUREFILTER_POINT_SAMPLED,GR_TEXTUREFILTER_POINT_SAMPLED);
        grTexMipMapMode(GR_TMU0,GR_MIPMAP_DISABLE,FXFALSE);grTexCombine(GR_TMU0,GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,FXFALSE,FXFALSE);
        grColorCombine(GR_COMBINE_FUNCTION_SCALE_OTHER,GR_COMBINE_FACTOR_LOCAL,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_TEXTURE,FXFALSE);
    }else grColorCombine(GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_NONE,FXFALSE);
}
static void draw_prepared(Prepared *draws,unsigned count){unsigned d,i;for(d=0;d<count;d++){grSstIdle();state_for(draws[d].source);for(i=0;i<draws[d].count;i+=3){__wrap_grDrawTriangle(draws[d].vertices+i,draws[d].vertices+i+1,draws[d].vertices+i+2);if(prepared_serial)__real_grSstIdle();}grSstIdle();}}
static int begin_buffer(uint32_t clear,unsigned slot){
    if(rd(control,8)!=0||log_start())return -1;frame_started=seconds();if(wr(12,4))return -1;
    configure();grRenderBuffer(slot?GR_BUFFER_BACKBUFFER:GR_BUFFER_FRONTBUFFER);
    grBufferClear(abgr(clear),0,GR_WDEPTHVALUE_FARTHEST);in_frame=1;return 0;
}
static int finish_buffer(void){
    double start;uint32_t state;
    defer_wait=0;grSstIdle();if(wr(12,1))return -1;start=seconds();
    do{state=rd(control,8);if(state&8||seconds()-start>3)return -1;}while(!(state&4));
    if(rd(sst,0x254)&7u)return -1;
    if(wr(12,2)||rd(control,8)!=0)return -1;
    in_frame=0;log_end();return 0;
}
static uint16_t stamp_value(unsigned frame){return ((frame&31)<<11)|(((frame>>5)&63)<<5)|31;}
static void stamp(unsigned frame){
    GrVertex a,b,c,d;float scale=render_scale;uint16_t value=stamp_value(frame);memset(&a,0,sizeof(a));
    a.r=((value>>11)&31)*8;a.g=((value>>5)&63)*4;a.b=248;a.a=255;a.oow=.95f;
    b=c=d=a;b.x=c.x=8;c.y=d.y=8;
    grDepthBufferFunction(GR_CMP_ALWAYS);grDepthMask(FXFALSE);grColorCombine(GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_NONE,FXFALSE);
    render_scale=1;__wrap_grDrawTriangle(&a,&b,&c);__wrap_grDrawTriangle(&a,&c,&d);render_scale=scale;
}
typedef struct {int occupied,ready;unsigned frame;double copied_ms;} Slot;
static Slot slots[2];static unsigned offset_bytes,completed,errors;static int done;
static unsigned char *gold;
static unsigned first_error[12][5],first_error_count;
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition=PTHREAD_COND_INITIALIZER;
static void *copy_frames(void *unused){
    uint32_t *copy=malloc(BYTES);unsigned x,y;int slot;(void)unused;
    for(;;){
        pthread_mutex_lock(&mutex);
        while(!slots[0].ready&&!slots[1].ready&&!done)pthread_cond_wait(&condition,&mutex);
        if(!slots[0].ready&&!slots[1].ready&&done){pthread_mutex_unlock(&mutex);break;}
        slot=slots[0].ready?0:1;if(slots[0].ready&&slots[1].ready&&slots[1].frame<slots[0].frame)slot=1;
        slots[slot].ready=0;pthread_mutex_unlock(&mutex);
        {double start=seconds();__asm__ __volatile__("dmb sy" ::: "memory");
        for(y=0;y<H;y++)for(x=0;x<W/2;x++)copy[y*W/2+x]=ddr[slot*offset_bytes/4+y*W/2+x];
        __asm__ __volatile__("dmb sy" ::: "memory");slots[slot].copied_ms=(seconds()-start)*1000;}
        for(y=0;y<H;y++)for(x=0;x<W;x++){
            const uint16_t *image=(const uint16_t *)copy,*reference=(const uint16_t *)gold;
            uint16_t wanted=x<8&&y<8?stamp_value(slots[slot].frame):reference[y*W+x];
            if(image[y*W+x]!=wanted){errors++;if(first_error_count<12){unsigned *e=first_error[first_error_count++];e[0]=slots[slot].frame;e[1]=x;e[2]=y;e[3]=wanted;e[4]=image[y*W+x];}}
        }
        pthread_mutex_lock(&mutex);slots[slot].occupied=0;completed++;pthread_cond_broadcast(&condition);pthread_mutex_unlock(&mutex);
    }
    free(copy);return NULL;
}
int main(int argc,char **argv){
    uint32_t header[6],texture[3],d,i;FILE *f;ReplayDraw *draws;Prepared *prepared;unsigned char *rgba;double prepare_start,prepare_ms,start,elapsed;pthread_t copier;unsigned iterations;
    if(argc!=3&&argc!=4)return 2;iterations=atoi(argv[2]);if(iterations<10||iterations>2000)return 2;
    f=fopen(argv[1],"rb");if(!f)return 2;get(f,header,24);if(memcmp(header,"RPL1",4)||header[1]!=W||header[2]!=H)return 2;
    setenv("SPINAL_WBUFFER","1",1);if(fg_open(W,H))return 3;
    if(getenv("SAMPLE_SCALE")){render_scale=strtod(getenv("SAMPLE_SCALE"),NULL);if(render_scale<.5f||render_scale>1)return 2;}
    ddr=mmap(NULL,4*1024*1024,PROT_READ,MAP_SHARED,mem_fd,0x3f400000ULL);if(ddr==MAP_FAILED)return 3;
    for(i=0;i<header[4];i++){unsigned char *data;get(f,texture,12);data=malloc(texture[1]*texture[2]*4);get(f,data,texture[1]*texture[2]*4);if(fg_upload(texture[0],texture[1],texture[2],data))return 4;free(data);}
    draws=calloc(header[5],sizeof(*draws));prepared=calloc(header[5],sizeof(*prepared));rgba=malloc(W*H*4);gold=malloc(BYTES);
    for(d=0;d<header[5];d++){ReplayDraw *r=draws+d;get(f,r,20);r->v=malloc(r->nv*36);r->ix=malloc(r->ni*4);get(f,r->v,r->nv*36);get(f,r->ix,r->ni*4);prepared[d].source=r;}fclose(f);
    /* Unmodified serialized bridge supplies hardware pixel reference. */
    serialize=1;if(fg_begin(header[3]))return 4;
    for(d=0;d<header[5];d++){ReplayDraw *r=draws+d;if(fg_draw(r->v,r->nv,r->ix,r->ni,r->texture,r->depth,r->cull,0))return 4;}
    if(finish_direct(rgba))return 4;memcpy(gold,pixels,BYTES);
    if(getenv("EXPERIMENT_GOLDEN")){
        unsigned diff;FILE *reference=fopen(getenv("EXPERIMENT_GOLDEN"),"rb");if(!reference)return 2;get(reference,gold,BYTES);fclose(reference);diff=differences(gold,pixels);
        if(diff){fprintf(stderr,"Optimized setup changed %u serialized pixels\n",diff);fg_close();return 5;}
    }
    /* Measure preclipping/projection independently. No GPU triangle is drawn. */
    serialize=0;fast_clip=1;if(fg_begin(header[3]))return 4;triangle_sink=record_triangle;prepare_start=seconds();
    for(d=0;d<header[5];d++){ReplayDraw *r=draws+d;record_to=prepared+d;if(fg_draw(r->v,r->nv,r->ix,r->ni,r->texture,r->depth,r->cull,0))return 4;}
    prepare_ms=(seconds()-prepare_start)*1000;triangle_sink=NULL;if(finish_direct(rgba))return 4;
    prepared_serial=1;queue_sync=1;defer_wait=0;if(fg_begin(header[3]))return 4;draw_prepared(prepared,header[5]);defer_wait=0;if(finish_direct(rgba))return 4;
    fprintf(stderr,"Prepared single-buffer differences: %u\n",differences(gold,pixels));
    prepared_serial=0;offset_bytes=((rd(sst,0x218)>>11)&511)*4096;if(!offset_bytes||offset_bytes+BYTES>4*1024*1024||((rd(sst,0x214)>>4)&15)*64!=W||((rd(sst,0)>>10)&1))return 4;
    queue_sync=argc==4?atoi(argv[3]):1;if(queue_sync<1||queue_sync>8)return 2;if(pthread_create(&copier,NULL,copy_frames,NULL))return 4;start=seconds();
    for(i=0;i<iterations;i++){
        unsigned slot=i&1;pthread_mutex_lock(&mutex);while(slots[slot].occupied)pthread_cond_wait(&condition,&mutex);slots[slot].occupied=1;slots[slot].frame=i;pthread_mutex_unlock(&mutex);
        defer_wait=1;if(begin_buffer(header[3],slot))return 4;draw_prepared(prepared,header[5]);stamp(i);if(finish_buffer())return 4;
        pthread_mutex_lock(&mutex);slots[slot].ready=1;pthread_cond_broadcast(&condition);pthread_mutex_unlock(&mutex);
    }
    pthread_mutex_lock(&mutex);done=1;pthread_cond_broadcast(&condition);pthread_mutex_unlock(&mutex);pthread_join(copier,NULL);elapsed=seconds()-start;
    printf("{\"frames\":%u,\"seconds\":%.9f,\"fps\":%.6f,\"captured\":%u,\"pixel_errors\":%u,\"prepare_ms\":%.6f,\"render_scale\":%.3f,\"static_prepared_geometry\":true,\"double_buffered\":true,\"first_errors\":[",iterations,elapsed,iterations/elapsed,completed,errors,prepare_ms,render_scale);
    for(i=0;i<first_error_count;i++)printf("%s[%u,%u,%u,%u,%u]",i?",":"",first_error[i][0],first_error[i][1],first_error[i][2],first_error[i][3],first_error[i][4]);printf("]}\n");
    munmap((void *)ddr,4*1024*1024);fg_close();return errors||completed!=iterations?5:0;
}
