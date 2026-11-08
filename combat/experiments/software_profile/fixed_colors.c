/* Experimental wrapper around the pinned, licensed Glide setup translation
 * unit. Geometry, W, textures and varying colors retain their float writes.
 * Flat RGB constants and zero gradients can use the existing fixed aliases.
 * Not enabled in the deployed build unless image equivalence passes. */
#include <stdint.h>
#include <3dfx.h>
#include <glidesys.h>
#define FX_DLL_DEFINITION
#include <fxdll.h>
#include <glide.h>
#include "fxglide.h"
extern int flighting_flat_colors;
static inline void flat_write(volatile void *address,unsigned offset,float value){
    if(flighting_flat_colors){
        switch(offset){
        case 0xa0:case 0xa4:case 0xa8:
            if(value>=0&&value<=255){*(volatile uint32_t *)((uintptr_t)address-0x80)=(uint32_t)(value*4096.0f);return;}break;
        case 0xc0:case 0xc4:case 0xc8:case 0xe0:case 0xe4:case 0xe8:
            if(value==0){*(volatile uint32_t *)((uintptr_t)address-0x80)=0;return;}break;
        }
    }
    *(volatile float *)address=value;
}
#undef GR_SETF
#define GR_SETF(d,s) {flat_write((volatile void *)&(d),(unsigned)((uintptr_t)&(d)-(uintptr_t)hw)&0xfff,(s));GR_INC_SIZE(4);}
#include "gxdraw.c"
