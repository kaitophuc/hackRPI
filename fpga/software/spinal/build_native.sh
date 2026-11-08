#!/bin/sh
# Prepared source must have glide-headless.patch applied; do not modify upstream.
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$task_dir/../.." && pwd)
source_dir=${1:-$project_dir/build/spinal-native-src}
glide_dir=$source_dir/emu/glide
driver_dir=$glide_dir/glide2x/sst1/glide/src
test -f "$source_dir/.platform-source.json"
grep -q DE10_HEADLESS "$driver_dir/Makefile.de10"
mkdir -p "$glide_dir/glide2x/sst1/lib/de10"
make -C "$driver_dir" -f Makefile.de10 HEADLESS=1 CC="${CC:-cc}" AR="${AR:-ar}" \
    EXTRA_CFLAGS="-std=gnu99 -march=armv7-a ${GPU_CFLAGS:-}" ../../lib/de10/libglide2x.a
"${CC:-cc}" -std=c99 -O2 -march=armv7-a -Wall -Wextra -Werror \
    -DDE10_BACKEND -DDE10_HEADLESS -DSST1 \
    -I"$driver_dir" -I"$glide_dir/glide2x/sst1/incsrc" \
    -I"$glide_dir/glide2x/sst1/init" -I"$glide_dir/swlibs/fxmisc" \
    -I"$glide_dir/swlibs/newpci/pcilib" \
    "$task_dir/spinal_capture.c" "$project_dir/software/mmio_access.c" \
    "$glide_dir/glide2x/sst1/lib/de10/libglide2x.a" -lm -lrt \
    -o "$task_dir/spinal_capture"
"${CC:-cc}" -std=c99 -O2 -march=armv7-a -Wall -Wextra -Werror \
    "$task_dir/enable_ddr_ports.c" "$project_dir/software/mmio_access.c" \
    -o "$task_dir/enable_ddr_ports"
"${CC:-cc}" -std=c99 -O2 -march=armv7-a -Wall -Wextra -Werror \
    "$task_dir/inspect_ddr_rules.c" "$project_dir/software/mmio_access.c" \
    -o "$task_dir/inspect_ddr_rules"
"${CC:-cc}" -std=c99 -O2 -march=armv7-a -Wall -Wextra -Werror \
    "$task_dir/probe_sst.c" "$project_dir/software/mmio_access.c" \
    -o "$task_dir/probe_sst"
