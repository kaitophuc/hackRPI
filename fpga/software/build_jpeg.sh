#!/bin/sh
set -eu
cd "$(dirname "$0")"
${CC:-cc} -std=c99 -O2 -Wall -Wextra -Werror jpeg_benchmark.c -o jpeg_benchmark -ljpeg -lrt
