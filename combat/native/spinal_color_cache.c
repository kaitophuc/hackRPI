/* Keep the pinned Glide arithmetic and floating-point register values. Only
 * omit identical flat RGB writes within a draw; reset at draw/state changes.
 * The included translation unit retains its upstream license and notices. */
#include <stdint.h>
#include <string.h>
#include <3dfx.h>
#include <glidesys.h>
#define FX_DLL_DEFINITION
#include <fxdll.h>
#include <glide.h>
#include "fxglide.h"
extern int flighting_flat_colors;
extern unsigned flighting_color_epoch;
static unsigned cached_epoch,valid;
static uint32_t cached[9];
static inline void cached_write(volatile void *address,unsigned offset,float value){
    if(flighting_flat_colors){
        unsigned slot=9;
        switch(offset){
        case 0xa0:slot=0;break;case 0xa4:slot=1;break;case 0xa8:slot=2;break;
        case 0xc0:slot=3;break;case 0xc4:slot=4;break;case 0xc8:slot=5;break;
        case 0xe0:slot=6;break;case 0xe4:slot=7;break;case 0xe8:slot=8;break;
        }
        if(slot<9){uint32_t bits;unsigned mask=1u<<slot;memcpy(&bits,&value,sizeof(bits));
            if(cached_epoch!=flighting_color_epoch){valid=0;cached_epoch=flighting_color_epoch;}
            if((valid&mask)&&cached[slot]==bits)return;
            cached[slot]=bits;valid|=mask;
        }
    }
    *(volatile float *)address=value;
}
#undef GR_SETF
#define GR_SETF(d,s) {cached_write((volatile void *)&(d),(unsigned)((uintptr_t)&(d)-(uintptr_t)hw)&0xfff,(s));GR_INC_SIZE(4);}
#include "gxdraw.c"
