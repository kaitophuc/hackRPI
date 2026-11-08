#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
glide=${SPINAL_GLIDE_ROOT:-$root/fpga/build/spinal-native-src/emu/glide}
driver=$glide/glide2x/sst1/glide/src
test -f "$glide/glide2x/sst1/lib/de10/libglide2x.a"
mkdir -p "$root/combat/dist"
extra_objects=""
if test "${SPINAL_COLOR_CACHE_BUILD:-1}" = 1; then
 mkdir -p "$root/build/software-profile"
 cc -std=gnu99 -O3 -fPIC -fno-strict-aliasing -mcpu=cortex-a9 -mfpu=neon -ffp-contract=off \
  -DINIT_LINUX -DDE10_BACKEND -DDE10_HEADLESS -DGLIDE_HARDWARE -DGLIDE_DEFAULT_GAMMA=1.3f -DGLIDE_LIB=1 -DSST1 -DGLIDE_USE_C_TRISETUP \
  -I"$driver" -I"$glide/glide2x/sst1/incsrc" -I"$glide/glide2x/sst1/init" -I"$glide/glide2x/sst1/init/initvg" \
  -I"$glide/swlibs/fxmisc" -I"$glide/swlibs/newpci/pcilib" -I"$glide/swlibs/fxmemmap" \
  -c "$root/combat/native/spinal_color_cache.c" -o "$root/build/software-profile/cached-colors.o"
 extra_objects="$root/build/software-profile/cached-colors.o"
fi
# Preserve floating-point operation order; do not enable fast-math or contraction.
cc -std=c99 -O3 -mcpu=cortex-a9 -mfpu=neon -ffp-contract=off -fPIC -Wall -Wextra -Werror \
 -DDE10_BACKEND -DDE10_HEADLESS -DSST1 \
 -I"$driver" -I"$glide/glide2x/sst1/incsrc" -I"$glide/glide2x/sst1/init" \
 -I"$glide/swlibs/fxmisc" -I"$glide/swlibs/newpci/pcilib" \
 -shared "$root/combat/native/spinal_pipeline.c" "$root/fpga/software/mmio_access.c" \
 $extra_objects "$glide/glide2x/sst1/lib/de10/libglide2x.a" -lm -lrt -pthread -Wl,--wrap=fprintf -Wl,--wrap=grSstIdle -Wl,--wrap=grDrawTriangle \
 -o "$root/combat/dist/libflighting_spinal_bridge.so.next"
mv "$root/combat/dist/libflighting_spinal_bridge.so.next" "$root/combat/dist/libflighting_spinal_bridge.so"
