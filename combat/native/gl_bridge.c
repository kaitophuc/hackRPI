/* Original MIT-licensed glue. RasterIX is external; its own license applies.
 * No fake RasterIX implementation or desktop fallback is provided.
 */
#include "flighting_bridge.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#ifdef _WIN32
#define GL_CALL __stdcall
#else
#define GL_CALL
#endif
typedef unsigned int U;
#define FN(ret,name,args) typedef ret (GL_CALL *name##_fn) args; static name##_fn p_##name
FN(void,glViewport,(int,int,int,int));
FN(void,glMatrixMode,(U)); FN(void,glLoadIdentity,(void));
FN(void,glEnable,(U)); FN(void,glDisable,(U));
FN(void,glDepthFunc,(U)); FN(void,glDepthMask,(unsigned char));
FN(void,glFrontFace,(U)); FN(void,glCullFace,(U));
FN(void,glClearColor,(float,float,float,float)); FN(void,glClear,(U));
FN(void,glGenTextures,(int,U*)); FN(void,glDeleteTextures,(int,const U*));
FN(void,glBindTexture,(U,U)); FN(void,glTexParameteri,(U,U,int));
FN(void,glTexEnvi,(U,U,int)); FN(void,glPixelStorei,(U,int));
FN(void,glTexImage2D,(U,int,int,int,int,int,U,U,const void*));
FN(void,glBegin,(U)); FN(void,glEnd,(void));
FN(void,glColor3f,(float,float,float)); FN(void,glTexCoord2f,(float,float));
FN(void,glVertex4f,(float,float,float,float));
FN(void,glFinish,(void)); FN(void,glReadPixels,(int,int,int,int,U,U,void*));
FN(U,glGetError,(void));
static int fg_w,fg_h,opened;static U textures[256];
static uint8_t *readback;
static int check(const char *operation) {
    U error=p_glGetError();
    if(error) {fprintf(stderr,"RasterIX bridge: %s GL error 0x%x\n",operation,error);return error==0x500?-2:-3;}
    return 0;
}
#define LOAD(name) do {p_##name=(name##_fn)fg_platform_get_proc(#name);if(!p_##name) {fprintf(stderr,"RasterIX missing entry point: %s\n",#name);fg_close();return -2;}} while(0)
int fg_abi_version(void) {return 1;}
const char *fg_backend_name(void) {return fg_platform_backend_name();}
int fg_open(int w,int h) {
    if(opened||w<64||h<64||w>1920||h>1080)return -1;
    if(fg_platform_open(w,h))return -4;opened=1;fg_w=w;fg_h=h;
    LOAD(glViewport);LOAD(glMatrixMode);LOAD(glLoadIdentity);LOAD(glEnable);LOAD(glDisable);
    LOAD(glDepthFunc);LOAD(glDepthMask);LOAD(glFrontFace);LOAD(glCullFace);
    LOAD(glClearColor);LOAD(glClear);LOAD(glGenTextures);LOAD(glDeleteTextures);LOAD(glBindTexture);
    LOAD(glTexParameteri);LOAD(glTexEnvi);LOAD(glPixelStorei);LOAD(glTexImage2D);
    LOAD(glBegin);LOAD(glEnd);LOAD(glColor3f);LOAD(glTexCoord2f);LOAD(glVertex4f);
    LOAD(glFinish);LOAD(glReadPixels);LOAD(glGetError);
    readback=(uint8_t*)malloc((size_t)w*h*4);if(!readback) {fg_close();return -5;}
    memset(textures,0,sizeof(textures));
    p_glViewport(0,0,w,h);p_glMatrixMode(0x1701);p_glLoadIdentity();p_glMatrixMode(0x1700);p_glLoadIdentity();
    p_glDepthFunc(0x201);p_glFrontFace(0x901);p_glCullFace(0x405);
    p_glDisable(0xBE2); /* BLEND */ p_glDisable(0xB50); /* LIGHTING */
    p_glDisable(0xBC0); /* ALPHA_TEST */ p_glDisable(0xB60); /* FOG */
    p_glPixelStorei(0xCF5,1);p_glPixelStorei(0xD05,1); /* UNPACK/PACK alignment */
    {int error=check("initialize");if(error)fg_close();return error;}
}
int fg_upload(int id,int w,int h,const uint8_t *rgba) {
    uint8_t *flipped;int y,error;
    if(!opened||id<1||id>255||!rgba||w<1||w>256||h<1||h>256||(w&(w-1))||(h&(h-1)))return -1;
    flipped=(uint8_t*)malloc((size_t)w*h*4);if(!flipped)return -5;
    for(y=0;y<h;y++)memcpy(flipped+(size_t)y*w*4,rgba+(size_t)(h-1-y)*w*4,(size_t)w*4);
    if(!textures[id])p_glGenTextures(1,&textures[id]);
    p_glBindTexture(0xDE1,textures[id]);
    p_glTexParameteri(0xDE1,0x2801,0x2600); /* MIN / NEAREST */
    p_glTexParameteri(0xDE1,0x2800,0x2600); /* MAG / NEAREST */
    p_glTexParameteri(0xDE1,0x2802,0x812F); /* WRAP_S / CLAMP_TO_EDGE */
    p_glTexParameteri(0xDE1,0x2803,0x812F); /* WRAP_T / CLAMP_TO_EDGE */
    p_glTexEnvi(0x2300,0x2200,0x2100); /* ENV_MODE / MODULATE */
    p_glTexImage2D(0xDE1,0,0x1908,w,h,0,0x1908,0x1401,flipped);free(flipped);
    error=check("texture upload");return error;
}
int fg_begin(uint32_t argb) {
    if(!opened)return -4;
    p_glDepthMask(1);p_glClearColor(((argb>>16)&255)/255.0f,((argb>>8)&255)/255.0f,(argb&255)/255.0f,1);
    p_glClear(0x4000|0x100);return check("clear");
}
int fg_draw(const float *v,int nv,const int32_t *indices,int ni,int tex,int depth,int cull,int wire) {
    int i;
    if(!opened||!v||!indices||nv<0||ni<0||ni%3||tex<0||tex>255)return -1;
    if(wire)return -2; /* Optional desktop debug; no unapproved GL polygon mode. */
    if(tex&&!textures[tex])return -1;
    for(i=0;i<ni;i++)if(indices[i]<0||indices[i]>=nv)return -1;
    if(depth)p_glEnable(0xB71);else p_glDisable(0xB71);p_glDepthMask(depth?1:0);
    if(cull)p_glEnable(0xB44);else p_glDisable(0xB44);
    if(tex) {p_glEnable(0xDE1);p_glBindTexture(0xDE1,textures[tex]);}else p_glDisable(0xDE1);
    p_glBegin(4); /* TRIANGLES */
    for(i=0;i<ni;i++) {const float *a=v+(size_t)indices[i]*9;p_glColor3f(a[4],a[5],a[6]);p_glTexCoord2f(a[7],a[8]);p_glVertex4f(a[0],a[1],a[2],a[3]);}
    p_glEnd();return check("triangles");
}
int fg_end(uint8_t *output,int length) {
    int y,error;
    if(!opened||!output||length!=fg_w*fg_h*4)return -1;
    p_glFinish();p_glReadPixels(0,0,fg_w,fg_h,0x1908,0x1401,readback);
    error=check("finish/readback");if(error)return error;
    for(y=0;y<fg_h;y++)memcpy(output+(size_t)y*fg_w*4,readback+(size_t)(fg_h-1-y)*fg_w*4,(size_t)fg_w*4);
    return 0;
}
int fg_present(const uint8_t *output,int length) {
    if(!opened||!output||length!=fg_w*fg_h*4)return -1;
    return fg_platform_present(output,fg_w,fg_h)?-4:0;
}
void fg_close(void) {
    int i;if(!opened)return;
    if(p_glDeleteTextures)for(i=1;i<256;i++)if(textures[i])p_glDeleteTextures(1,&textures[i]);
    free(readback);readback=NULL;fg_platform_close();opened=0;
}
