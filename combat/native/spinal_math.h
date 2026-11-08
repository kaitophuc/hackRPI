#ifndef FLIGHTING_SPINAL_MATH_H
#define FLIGHTING_SPINAL_MATH_H
#include <math.h>
#include <string.h>
typedef struct { double v[9]; } FgVertex;
static double fg_plane(const FgVertex *v,int p) {
    const double *a=v->v;
    switch(p){case 0:return a[3]-1e-7;case 1:return a[3]+a[0];case 2:return a[3]-a[0];case 3:return a[3]+a[1];case 4:return a[3]-a[1];case 5:return a[3]+a[2];default:return a[3]-a[2];}
}
/* Homogeneous clipping changes geometry only; every covered pixel is produced
 * by the FPGA. Interpolate raw attributes before perspective division. */
static int fg_clip_triangle(const FgVertex *input,FgVertex *output) {
    FgVertex a[16],b[16]; int n=3,p,i,j;
    memcpy(a,input,3*sizeof(*a));
    for(p=0;p<7&&n;p++) {
        int count=0; FgVertex previous=a[n-1]; double da=fg_plane(&previous,p);
        for(i=0;i<n;i++) {
            FgVertex current=a[i]; double db=fg_plane(&current,p);
            if((da>=0)!=(db>=0)) {double t=da/(da-db);if(count>=16)return -1;for(j=0;j<9;j++)b[count].v[j]=previous.v[j]+(current.v[j]-previous.v[j])*t;count++;}
            if(db>=0){if(count>=16)return -1;b[count++]=current;}
            previous=current;da=db;
        }
        n=count;memcpy(a,b,(size_t)n*sizeof(*a));
    }
    memcpy(output,a,(size_t)n*sizeof(*output));return n;
}
static double fg_screen_area(const FgVertex *a,const FgVertex *b,const FgVertex *c) {
    double ax=a->v[0]/a->v[3],ay=a->v[1]/a->v[3];
    double bx=b->v[0]/b->v[3],by=b->v[1]/b->v[3];
    return (bx-ax)*(c->v[1]/c->v[3]-ay)-(by-ay)*(c->v[0]/c->v[3]-ax);
}
#endif
