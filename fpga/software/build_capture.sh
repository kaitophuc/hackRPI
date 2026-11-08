#!/bin/sh
# Native HPS GCC build; compatible with C99/GCC 4.9 and Python 2-only images.
set -eu
cd "$(dirname "$0")"
"${CC:-cc}" -std=c99 -march=armv7-a -Wall -Wextra -Werror -O2 capture.c mmio_access.c -o capture -lrt
