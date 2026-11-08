#!/bin/sh
set -eu
root=/root/hackrpi
glide=$root/fpga/build/spinal-native-src/emu/glide
driver=$glide/glide2x/sst1/glide/src
mkdir -p "$root/build/batching"
sample=${1:-probe}
test "$sample" = probe || test "$sample" = pipeline
extra_objects=""
suffix=""
if test "${OPTIMIZED_SETUP:-0}" = 1; then
 for unit in gdraw gxdraw; do
  cc -std=gnu99 -O3 -ffast-math -fno-associative-math -fno-strict-aliasing -mcpu=cortex-a9 -mfpu=neon \
   -DINIT_LINUX -DDE10_BACKEND -DDE10_HEADLESS -DGLIDE_HARDWARE -DGLIDE_DEFAULT_GAMMA=1.3f -DGLIDE_LIB=1 -DSST1 -DGLIDE_USE_C_TRISETUP \
   -I"$driver" -I"$glide/glide2x/sst1/incsrc" -I"$glide/glide2x/sst1/init" -I"$glide/glide2x/sst1/init/initvg" \
   -I"$glide/swlibs/fxmisc" -I"$glide/swlibs/newpci/pcilib" -I"$glide/swlibs/fxmemmap" \
   -c "$driver/$unit.c" -o "$root/build/batching/$unit-o3.o"
  extra_objects="$extra_objects $root/build/batching/$unit-o3.o"
 done
 suffix="-o3"
fi
cc -std=c99 -O2 -march=armv7-a -Wall -Wextra -Werror \
 -DDE10_BACKEND -DDE10_HEADLESS -DSST1 \
 -I"$driver" -I"$glide/glide2x/sst1/incsrc" -I"$glide/glide2x/sst1/init" \
 -I"$glide/swlibs/fxmisc" -I"$glide/swlibs/newpci/pcilib" \
 "$root/combat/experiments/batching/$sample.c" "$root/fpga/software/mmio_access.c" \
 $extra_objects "$glide/glide2x/sst1/lib/de10/libglide2x.a" -lm -lrt -Wl,--wrap=fprintf -Wl,--wrap=grDrawTriangle -Wl,--wrap=grSstIdle \
 -pthread -o "$root/build/batching/$sample$suffix"
