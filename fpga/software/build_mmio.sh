#!/bin/sh
# Run on the HPS using its native GCC; no downloaded dependencies.
set -eu
cd "$(dirname "$0")"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -O2 -fPIC -shared mmio_access.c -o libgpu_mmio.so
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -O2 -DGPU_MMIO_SELF_TEST mmio_access.c -o mmio_self_test
./mmio_self_test
