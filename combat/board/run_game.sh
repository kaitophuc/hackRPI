#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
export MONO_CFG_DIR="$root/runtime/etc"
export MONO_PATH="$root/runtime/usr/lib/mono/4.5"
export LD_LIBRARY_PATH="$root/combat/dist${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$root/runtime/usr/bin/mono-sgen" "$root/combat/dist/Flighting.Headless.exe" "$@"
