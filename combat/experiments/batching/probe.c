/* Standalone experiment: includes the unchanged game bridge in this binary.
 * No game .so, C# source or FPGA bitstream is modified by this sample. */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "../../native/spinal_math.h"
static int fast_clip;
static int experimental_clip(const FgVertex *input,FgVertex *output){
    int common=127,combined=0,i,p;
    if(fast_clip){
        for(i=0;i<3;i++){int code=0;for(p=0;p<7;p++)if(fg_plane(input+i,p)<0)code|=1<<p;common&=code;combined|=code;}
        if(common)return 0;
        if(!combined){memcpy(output,input,3*sizeof(*input));return 3;}
    }
    return fg_clip_triangle(input,output);
}
#define fg_clip_triangle experimental_clip
#include "../../native/spinal_bridge.c"
#undef fg_clip_triangle
static int queue_sync;
static int defer_wait;
static float render_scale=1.0f;
extern void __real_grSstIdle(void);
void __wrap_grSstIdle(void){if(defer_wait)gpu_mmio_write32(sst,4096,0x120,0);else __real_grSstIdle();}
extern void __real_grDrawTriangle(const GrVertex *,const GrVertex *,const GrVertex *);
static void (*triangle_sink)(const GrVertex *,const GrVertex *,const GrVertex *);
void __wrap_grDrawTriangle(const GrVertex *a,const GrVertex *b,const GrVertex *c){
    if(triangle_sink){triangle_sink(a,b,c);return;}
    if(render_scale!=1.0f){GrVertex aa=*a,bb=*b,cc=*c;aa.x*=render_scale;aa.y*=render_scale;bb.x*=render_scale;bb.y*=render_scale;cc.x*=render_scale;cc.y*=render_scale;__real_grDrawTriangle(&aa,&bb,&cc);}
    else __real_grDrawTriangle(a,b,c);
    /* Queue the hardware's ordered SYNC/NOP. CPU proceeds into FIFO instead
     * of polling until the whole device becomes idle after every triangle. */
    {int n;for(n=0;n<queue_sync;n++)gpu_mmio_write32(sst,4096,0x120,0);}
}
typedef struct {uint32_t nv,ni,texture,depth,cull;float *v;int32_t *ix;} ReplayDraw;
static void get(FILE *f,void *out,size_t bytes){if(fread(out,1,bytes,f)!=bytes){fprintf(stderr,"Truncated sample\n");exit(2);}}
static unsigned differences(const unsigned char *a,const unsigned char *b){unsigned i,n=0;for(i=0;i<BYTES;i+=2)if(a[i]!=b[i]||a[i+1]!=b[i+1])n++;return n;}
static void save(const char *prefix,int mode,const unsigned char *data){char path[1024];FILE *f;snprintf(path,sizeof(path),"%s-%d.rgb565",prefix,mode);f=fopen(path,"wb");if(!f)exit(2);fwrite(data,1,BYTES,f);fclose(f);}
static volatile uint32_t *ddr;
static int finish_direct(unsigned char *rgba){
    uint32_t stride,offset,display,back;unsigned x,y;double start;int i;
    grSstIdle();if(fence())return -3;
    gpu_sequence=rd(control,0x20);render_cycles=rd(control,0x24);busy_cycles=rd(control,0x2c);
    stride=((rd(sst,0x214)>>4)&15u)*64u;
    offset=((rd(sst,0x218)>>11)&511u)*4096u;display=(rd(sst,0)>>10)&1u;back=display?0:offset;
    if(stride!=W||!offset||back+stride*H*2>4u*1024u*1024u)return -3;
    start=seconds();__asm__ __volatile__("dmb sy" ::: "memory");
    for(y=0;y<H;y++)for(x=0;x<W/2;x++){
        uint32_t pair=ddr[back/4+y*stride/2+x];unsigned at=y*W*2+x*4;
        pixels[at]=pair;pixels[at+1]=pair>>8;pixels[at+2]=pair>>16;pixels[at+3]=pair>>24;
    }
    __asm__ __volatile__("dmb sy" ::: "memory");copy_seconds=seconds()-start;
    if(rd(control,0x20)!=gpu_sequence||(rd(control,8)&14u)!=4u||(rd(sst,0x254)&7u))return -3;
    if(wr(12,2)||rd(control,8)!=0)return -3;
    capture_seconds=seconds()-frame_started;in_frame=0;frame_ready=1;sequence++;log_end();
    for(i=0;i<W*H;i++){unsigned v=pixels[i*2]|((unsigned)pixels[i*2+1]<<8);unsigned r=(v>>11)&31,g=(v>>5)&63,b=v&31;rgba[i*4]=(r<<3)|(r>>2);rgba[i*4+1]=(g<<2)|(g>>4);rgba[i*4+2]=(b<<3)|(b>>2);rgba[i*4+3]=255;}
    return 0;
}
int main(int argc,char **argv){
    uint32_t header[6],t[3],d,i;ReplayDraw *draws;FILE *f;unsigned char *rgba,*reference;int mode,iteration,count;
    if(argc!=4&&argc!=5){fprintf(stderr,"usage: probe sample.rpl output-prefix repetitions [direct-ddr=1]\n");return 2;}
    count=atoi(argv[3]);if(count<1||count>1000)return 2;
    f=fopen(argv[1],"rb");if(!f)return 2;get(f,header,sizeof(header));
    if(memcmp(header,"RPL1",4)||header[1]!=W||header[2]!=H||header[4]>255||header[5]>4096)return 2;
    setenv("SPINAL_WBUFFER","1",1);if(fg_open(W,H)){fprintf(stderr,"Cannot acquire verified GPU2\n");return 3;}
    if(argc==5&&atoi(argv[4])){ddr=mmap(NULL,4*1024*1024,PROT_READ,MAP_SHARED,mem_fd,0x3f400000ULL);if(ddr==MAP_FAILED)return 3;}
    for(i=0;i<header[4];i++){unsigned char *data;get(f,t,sizeof(t));if(t[1]>256||t[2]>256)return 2;data=malloc(t[1]*t[2]*4);get(f,data,t[1]*t[2]*4);if(fg_upload(t[0],t[1],t[2],data))return 4;free(data);}
    draws=calloc(header[5],sizeof(*draws));rgba=malloc(W*H*4);reference=malloc(BYTES);
    for(d=0;d<header[5];d++){ReplayDraw *r=draws+d;get(f,r,20);if(r->nv>750000||r->ni>750000)return 2;r->v=malloc(r->nv*36);r->ix=malloc(r->ni*4);get(f,r->v,r->nv*36);get(f,r->ix,r->ni*4);}fclose(f);
    for(mode=0;mode<5;mode++){
        serialize=mode==0;queue_sync=mode>=2;fast_clip=mode>=3;
        for(iteration=-2;iteration<count;iteration++){
            double a=seconds(),b,c,e;unsigned diff=0;
            defer_wait=mode>=4;
            if(fg_begin(header[3]))return 4;b=seconds();
            for(d=0;d<header[5];d++){ReplayDraw *r=draws+d;if(fg_draw(r->v,r->nv,r->ix,r->ni,r->texture,r->depth,r->cull,0))return 4;}
            c=seconds();defer_wait=0;if(ddr?finish_direct(rgba):fg_end(rgba,W*H*4))return 4;e=seconds();
            if(mode==0&&iteration==-2)memcpy(reference,pixels,BYTES);else diff=differences(reference,pixels);
            if(iteration>=0)printf("{\"mode\":%d,\"iteration\":%d,\"total_ms\":%.6f,\"clear_ms\":%.6f,\"draw_ms\":%.6f,\"finish_ms\":%.6f,\"copy_ms\":%.6f,\"fpga_busy_ms\":%.6f,\"render_ms\":%.6f,\"triangles\":%u,\"different_pixels\":%u}\n",mode,iteration,(e-a)*1000,(b-a)*1000,(c-b)*1000,(e-c)*1000,copy_seconds*1000,busy_cycles/50000.0,render_cycles/50000.0,submitted,diff);
            fflush(stdout);
        }
        save(argv[2],mode,pixels);
    }
    if(ddr)munmap((void *)ddr,4*1024*1024);fg_close();return 0;
}
