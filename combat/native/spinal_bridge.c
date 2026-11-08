/* SPDX-License-Identifier: MIT
 * FG native ABI1 implemented on the tested Standard GPU2/ARM Glide stack.
 * No software rasterizer, GL driver, presenter or browser rendering fallback.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "flighting_bridge.h"
#include "spinal_math.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdarg.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <glide.h>

extern int gpu_mmio_read32(void *,size_t,size_t,uint32_t *);
extern int gpu_mmio_write32(void *,size_t,size_t,uint32_t);

/* The bring-up library prints enter/exit for EVERY idle wait. Keep its error
 * diagnostics, but avoid thousands of formatting/write syscalls per frame.
 * --wrap affects only this library's references, not the managed process. */
int __wrap_fprintf(FILE *stream,const char *format,...){
    va_list args;int result;
    if(!getenv("FLIGHTING_VERBOSE_IDLE")&&
       (strncmp(format,"[de10] sst1InitIdle: enter",24)==0||
        strncmp(format,"[de10] sst1InitIdle: exit",23)==0))return 0;
    va_start(args,format);result=vfprintf(stream,format,args);va_end(args);return result;
}
enum {W=320,H=240,BYTES=W*H*2,MAX_TEX=256};
typedef struct {GrTexInfo info;FxU32 address;int allocated,valid;} TextureSlot;
static TextureSlot textures[MAX_TEX];
static unsigned char pixels[BYTES];
static void *control=MAP_FAILED,*sst=MAP_FAILED;
static int lock_fd=-1,mem_fd=-1,initialized,opened,in_frame,frame_ready;
static int width,height,serialize=1,wbuffer;
static uint32_t allocation,sequence,gpu_sequence,render_cycles,clock_hz,busy_cycles,submitted,clipped,culled;
static double frame_started,copy_seconds,capture_seconds;
static long long game_tick;static int health=100,kills,paused,game_over;static double distance;
static int sensor_fresh,sensor_ready,sensor_calibrating;static long long sensor_samples;static double sensor_roll,sensor_pitch;
static double geometry_ms,host_submit_ms;
static int saved_out=-1,saved_error=-1,log_fd=-1;
static int log_start(void){
    const char *path=getenv("FLIGHTING_GLIDE_LOG");
    if(saved_out>=0)return 0;
    if(!path)path="/tmp/hackrpi-glide.log";
    log_fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);if(log_fd<0)return -1;
    fflush(NULL);saved_out=dup(1);saved_error=dup(2);
    if(saved_out<0||saved_error<0)return -1;
    if(dup2(log_fd,1)<0||dup2(log_fd,2)<0)return -1;return 0;
}
static void log_end(void){
    fflush(NULL);
    if(saved_out>=0){dup2(saved_out,1);close(saved_out);saved_out=-1;}
    if(saved_error>=0){dup2(saved_error,2);close(saved_error);saved_error=-1;}
    if(log_fd>=0){close(log_fd);log_fd=-1;}
}

static double seconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;return t.tv_sec+t.tv_nsec/1e9;}
static uint32_t rd(void *map,unsigned offset){uint32_t v=0;if(gpu_mmio_read32(map,4096,offset,&v))return 0xffffffffu;return v;}
static int wr(unsigned offset,uint32_t value){return gpu_mmio_write32(control,4096,offset,value)?-3:0;}
static int fence(void){
    double start=seconds();struct timespec nap={0,1000000};
    if(wr(12,1))return -3;
    for(;;){uint32_t state=rd(control,8);if(state&~15u||state&8u)return -3;if(state&4u)return 0;if(seconds()-start>3)return -3;nanosleep(&nap,NULL);}
}
static FxU32 abgr(uint32_t argb){return (argb&0xff00ff00u)|((argb&255u)<<16)|((argb>>16)&255u);}
static void configure(void){
    grRenderBuffer(GR_BUFFER_BACKBUFFER);grClipWindow(0,0,W,H);grCullMode(GR_CULL_DISABLE);
    grDitherMode(GR_DITHER_DISABLE);grDepthBufferMode(wbuffer?GR_DEPTHBUFFER_WBUFFER:GR_DEPTHBUFFER_ZBUFFER);grDepthBufferFunction(wbuffer?GR_CMP_LEQUAL:GR_CMP_GREATER);grDepthBiasLevel(0);
    grDepthMask(FXTRUE);grColorMask(FXTRUE,FXFALSE);grAlphaTestFunction(GR_CMP_ALWAYS);
    grAlphaBlendFunction(GR_BLEND_ONE,GR_BLEND_ZERO,GR_BLEND_ONE,GR_BLEND_ZERO);
    grFogMode(GR_FOG_DISABLE);grChromakeyMode(GR_CHROMAKEY_DISABLE);
    grColorCombine(GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_NONE,FXFALSE);
}
FG_EXPORT int fg_abi_version(void){return 1;}
FG_EXPORT const char *fg_backend_name(void){return wbuffer?"SpinalVoodoo/FPGA/GPU2/92c56afa/RGB565/W16/320x240":"SpinalVoodoo/FPGA/GPU2/92c56afa/RGB565/Z16/320x240";}
FG_EXPORT void fg_close(void){
    if(control!=MAP_FAILED&&(rd(control,8)&4u))wr(12,2);
    if(initialized){log_start();grGlideShutdown();initialized=0;}log_end();
    if(control!=MAP_FAILED){munmap(control,4096);control=MAP_FAILED;}
    if(sst!=MAP_FAILED){munmap(sst,4096);sst=MAP_FAILED;}
    if(mem_fd>=0){close(mem_fd);mem_fd=-1;}if(lock_fd>=0){close(lock_fd);lock_fd=-1;}
    opened=in_frame=frame_ready=0;allocation=sequence=0;memset(textures,0,sizeof(textures));
}
FG_EXPORT int fg_open(int w,int h){
    GrHwConfiguration hardware;
    if(opened||w!=W||h!=H)return -1;width=w;height=h;
    lock_fd=open("/run/lock/de10-gpu-platform.lock",O_RDWR|O_CREAT,0600);
    if(lock_fd<0||flock(lock_fd,LOCK_EX|LOCK_NB))goto fail;
    mem_fd=open("/dev/mem",O_RDWR|O_SYNC);if(mem_fd<0)goto fail;
    control=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,mem_fd,0xff240000ULL);
    if(control==MAP_FAILED||rd(control,0)!=0x47505532u||rd(control,4)!=2||rd(control,0x10)!=W||rd(control,0x14)!=H||rd(control,0x18)!=W*2||rd(control,0x1c)!=1)goto fail;
    /* Require an explicitly audited/enabled, idle device; never release another
     * producer's frame or change DDR controller configuration here. */
    if(rd(control,8)!=0)goto fail;
    sst=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,mem_fd,0xc0000000ULL);
    if(sst==MAP_FAILED||(rd(sst,0x254)&7u))goto fail;
    setenv("DE10_VOODOO_BASE","0xc0000000",1);setenv("DE10_VOODOO_SPAN","0x01000000",1);
    setenv("DE10_ADV7513_INIT","0",1);setenv("GLIDE_X11_ENABLE","0",1);
    setenv("SST_FBIMEM_SIZE","4",1);setenv("SST_TMUMEM_SIZE","4",1);
    serialize=!(getenv("SPINAL_BATCH_TEST")&&strcmp(getenv("SPINAL_BATCH_TEST"),"1")==0);
    wbuffer=getenv("SPINAL_WBUFFER")&&strcmp(getenv("SPINAL_WBUFFER"),"1")==0;
    if(log_start())goto fail;grGlideInit();initialized=1;if(!grSstQueryHardware(&hardware))goto fail;grSstSelect(0);
    if(!grSstWinOpen(0,GR_RESOLUTION_320x240,GR_REFRESH_60Hz,GR_COLORFORMAT_ABGR,GR_ORIGIN_UPPER_LEFT,2,1))goto fail;
    grSstIdle();if(fence()||wr(12,2))goto fail;
    configure();grSstIdle();clock_hz=rd(control,0x28);if(clock_hz!=50000000u)goto fail;
    opened=1;log_end();return 0;
fail:fg_close();return -4;
}
FG_EXPORT int fg_upload(int id,int w,int h,const uint8_t *rgba){
    int i,lod=0,largest=w>h?w:h,delta=0,aspect;FxU32 required;FxU16 *data;TextureSlot *t;
    if(!opened||in_frame||!rgba||id<=0||id>=MAX_TEX||w<1||h<1||w>256||h>256||(w&(w-1))||(h&(h-1)))return -1;
    while((256>>lod)>largest)lod++;
    for(i=w;i>1;i>>=1)delta++;for(i=h;i>1;i>>=1)delta--;
    if(delta>3||delta< -3)return -2;aspect=3-delta;
    data=malloc((size_t)w*h*2);if(!data)return -5;
    for(i=0;i<w*h;i++){if(rgba[i*4+3]!=255){free(data);return -2;}data[i]=(FxU16)(((rgba[i*4]>>3)<<11)|((rgba[i*4+1]>>2)<<5)|(rgba[i*4+2]>>3));}
    t=&textures[id];memset(&t->info,0,sizeof(t->info));t->info.smallLod=t->info.largeLod=(GrLOD_t)lod;t->info.aspectRatio=(GrAspectRatio_t)aspect;t->info.format=GR_TEXFMT_RGB_565;t->info.data=data;
    required=grTexTextureMemRequired(GR_MIPMAPLEVELMASK_BOTH,&t->info);
    if(!t->valid||required>(FxU32)t->allocated){allocation=(allocation+7u)&~7u;if(required>4u*1024u*1024u-allocation){free(data);return -5;}t->address=allocation;t->allocated=(int)required;allocation+=required;}
    if(log_start()){free(data);return -4;}grSstIdle();grTexDownloadMipMap(GR_TMU0,t->address,GR_MIPMAPLEVELMASK_BOTH,&t->info);grSstIdle();
    free(data);t->info.data=NULL;t->valid=1;
    if(fence()||wr(12,2)){log_end();return -3;}log_end();return 0;
}
FG_EXPORT int fg_begin(uint32_t clear){
    if(!opened||in_frame||rd(control,8)!=0)return -4;
    if(log_start())return -4;frame_started=seconds();submitted=clipped=culled=0;frame_ready=0;
    if(wr(12,4))return -3;configure();grBufferClear(abgr(clear),0,wbuffer?GR_WDEPTHVALUE_FARTHEST:0);grSstIdle();in_frame=1;return 0;
}
static GrVertex project(const FgVertex *input){
    const double *p=input->v;GrVertex v;double inverse=1/p[3],depth=(1-(p[2]*inverse*.5+.5))*65535;
    memset(&v,0,sizeof(v));v.x=(float)((p[0]*inverse*.5+.5)*width);v.y=(float)((.5-p[1]*inverse*.5)*height);
    /* Contract near plane is 0.2m. Fill the positive 2.30 reciprocal-W
     * range without crossing 1.0 at the near plane. The common factor
     * cancels from texture perspective division. */
    v.ooz=(float)fmax(0,fmin(65535,depth));v.oow=(float)(inverse*.19);v.a=255;
    v.r=(float)fmax(0,fmin(255,p[4]*255));v.g=(float)fmax(0,fmin(255,p[5]*255));v.b=(float)fmax(0,fmin(255,p[6]*255));
    v.tmuvtx[0].oow=v.oow;return v;
}
FG_EXPORT int fg_draw(const float *vertices,int vertex_count,const int32_t *indices,int count,int texture,int depth,int cull,int wire){
    int i,j,k,n;TextureSlot *t=NULL;
    if(!in_frame||!vertices||!indices||vertex_count<0||vertex_count>750000||count<0||count>750000||count%3||texture<0||texture>=MAX_TEX)return -1;
    if(wire)return -2;if(texture&&!textures[texture].valid)return -1;
    for(i=0;i<vertex_count*9;i++)if(!isfinite(vertices[i]))return -1;
    for(i=0;i<count;i++)if(indices[i]<0||indices[i]>=vertex_count)return -1;
    grSstIdle();grDepthBufferFunction(depth?(wbuffer?GR_CMP_LEQUAL:GR_CMP_GREATER):GR_CMP_ALWAYS);grDepthMask(depth?FXTRUE:FXFALSE);
    if(texture){
        t=&textures[texture];grTexSource(GR_TMU0,t->address,GR_MIPMAPLEVELMASK_BOTH,&t->info);
        grTexClampMode(GR_TMU0,GR_TEXTURECLAMP_CLAMP,GR_TEXTURECLAMP_CLAMP);grTexFilterMode(GR_TMU0,GR_TEXTUREFILTER_POINT_SAMPLED,GR_TEXTUREFILTER_POINT_SAMPLED);
        grTexMipMapMode(GR_TMU0,GR_MIPMAP_DISABLE,FXFALSE);grTexCombine(GR_TMU0,GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,FXFALSE,FXFALSE);
        grColorCombine(GR_COMBINE_FUNCTION_SCALE_OTHER,GR_COMBINE_FACTOR_LOCAL,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_TEXTURE,FXFALSE);
    }else grColorCombine(GR_COMBINE_FUNCTION_LOCAL,GR_COMBINE_FACTOR_NONE,GR_COMBINE_LOCAL_ITERATED,GR_COMBINE_OTHER_NONE,FXFALSE);
    for(i=0;i<count;i+=3){
        FgVertex triangle[3],polygon[16];
        for(j=0;j<3;j++)for(k=0;k<9;k++)triangle[j].v[k]=vertices[indices[i+j]*9+k];
        n=fg_clip_triangle(triangle,polygon);if(n<0)return -3;if(n<3){culled++;continue;}if(n!=3)clipped++;
        for(j=1;j+1<n;j++){
            double area=fg_screen_area(&polygon[0],&polygon[j],&polygon[j+1]);GrVertex v[3];FgVertex *p[3]={&polygon[0],&polygon[j],&polygon[j+1]};
            if(fabs(area)<1e-12||(cull&&area<=0)){culled++;continue;}
            for(k=0;k<3;k++){v[k]=project(p[k]);if(t){v[k].tmuvtx[0].sow=(float)(fmax(0,fmin(1,p[k]->v[7]))*255*v[k].oow);v[k].tmuvtx[0].tow=(float)((1-fmax(0,fmin(1,p[k]->v[8])))*255*v[k].oow);}}
            grDrawTriangle(&v[0],&v[1],&v[2]);if(serialize)grSstIdle();submitted++;
        }
    }
    grSstIdle();return 0;
}
FG_EXPORT int fg_end(uint8_t *rgba,int length){
    int i;double start;
    if(!in_frame||!rgba||length!=W*H*4)return -1;
    grSstIdle();if(fence())return -3;gpu_sequence=rd(control,0x20);render_cycles=rd(control,0x24);busy_cycles=rd(control,0x2c);
    start=seconds();if(!grLfbReadRegion(GR_BUFFER_BACKBUFFER,0,0,W,H,W*2,pixels))return -3;
    if(rd(control,0x20)!=gpu_sequence||(rd(control,8)&14u)!=4u||(rd(sst,0x254)&7u))return -3;
    copy_seconds=seconds()-start;if(wr(12,2)||rd(control,8)!=0)return -3;
    capture_seconds=seconds()-frame_started;in_frame=0;frame_ready=1;sequence++;log_end();
    for(i=0;i<W*H;i++){unsigned v=pixels[i*2]|((unsigned)pixels[i*2+1]<<8);unsigned r=(v>>11)&31,g=(v>>5)&63,b=v&31;rgba[i*4]=(uint8_t)((r<<3)|(r>>2));rgba[i*4+1]=(uint8_t)((g<<2)|(g>>4));rgba[i*4+2]=(uint8_t)((b<<3)|(b>>2));rgba[i*4+3]=255;}
    return 0;
}
FG_EXPORT void fg_set_state(long long tick,int hp,int score,double travelled,int is_paused,int is_over){game_tick=tick;health=hp;kills=score;distance=travelled;paused=is_paused;game_over=is_over;}
FG_EXPORT void fg_set_sensor(int fresh,int ready,int calibrating,long long samples,double roll,double pitch){sensor_fresh=fresh;sensor_ready=ready;sensor_calibrating=calibrating;sensor_samples=samples;sensor_roll=roll;sensor_pitch=pitch;}
FG_EXPORT void fg_set_host_timing(double geometry,double submit){geometry_ms=geometry;host_submit_ms=submit;}
static int write_all(int fd,const void *buffer,size_t size){const unsigned char *p=buffer;while(size){ssize_t n=write(fd,p,size);if(n<0&&errno==EINTR)continue;if(n<=0)return -1;p+=n;size-=(size_t)n;}return 0;}
FG_EXPORT int fg_present(const uint8_t *rgba,int length){
    const char *path=getenv("FLIGHTING_FRAME_FILE");char temporary[1024],metadata[2048];uint32_t header[5];int size,fd,failed;
    if(!frame_ready||!rgba||length!=W*H*4)return -1;
    /* Capture-only diagnostics do not require a frame-exchange destination. */
    if(!path||!*path){frame_ready=0;return 0;}
    if(snprintf(temporary,sizeof(temporary),"%s.next",path)>=(int)sizeof(temporary))return -1;
    size=snprintf(metadata,sizeof(metadata),"{\"source\":\"hardware\",\"renderer\":\"SpinalVoodoo\",\"scene\":\"combat\",\"gpu_id\":1196447026,\"abi\":2,\"frame_sequence\":%u,\"gpu_sequence\":%u,\"render_cycles\":%u,\"clock_hz\":%u,\"pipeline_busy_cycles\":%u,\"copy_seconds\":%.9f,\"capture_seconds\":%.9f,\"submission_mode\":\"%s\",\"triangles_submitted\":%u,\"triangles_clipped\":%u,\"triangles_culled\":%u,\"tick\":%lld,\"health\":%d,\"kills\":%d,\"distance\":%.3f,\"paused\":%s,\"game_over\":%s,\"simulation_target_hz\":60,\"sensor_fresh\":%s,\"sensor_ready\":%s,\"sensor_calibrating\":%s,\"sensor_samples\":%lld,\"sensor_roll\":%.2f,\"sensor_pitch\":%.2f,\"geometry_ms\":%.3f,\"host_submit_ms\":%.3f}",sequence,gpu_sequence,render_cycles,clock_hz,busy_cycles,copy_seconds,capture_seconds,serialize?"serialized":"batch-test",submitted,clipped,culled,game_tick,health,kills,distance,paused?"true":"false",game_over?"true":"false",sensor_fresh?"true":"false",sensor_ready?"true":"false",sensor_calibrating?"true":"false",sensor_samples,sensor_roll,sensor_pitch,geometry_ms,host_submit_ms);
    if(size<0||size>=(int)sizeof(metadata))return -3;
    memcpy(header,"SFG1",4);header[1]=W;header[2]=H;header[3]=(uint32_t)size;header[4]=BYTES;
    fd=open(temporary,O_WRONLY|O_CREAT|O_TRUNC,0600);if(fd<0)return -4;
    failed=write_all(fd,header,sizeof(header))||write_all(fd,metadata,(size_t)size)||write_all(fd,pixels,BYTES)||fsync(fd);if(close(fd))failed=1;
    if(failed||rename(temporary,path))return -4;frame_ready=0;return 0;
}
