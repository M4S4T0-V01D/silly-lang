#!/bin/sh
# Bootstrap the self-hosted compiler and check that it reproduces itself.
#
#   stage 1: the reference compiler (Python) builds sillyc.silly
#   stage 2: stage 1 compiles sillyc.silly to C; gcc builds that
#   stage 3: stage 2 compiles sillyc.silly again; the C must equal stage 2's
#
# Usage: selfhost/bootstrap.sh [OUT_DIR]   (default: selfhost/build)
# The result is OUT_DIR/sillyc. Compile a program with it:
#   OUT_DIR/sillyc prog.silly prog.c && gcc -O2 -fwrapv -I selfhost prog.c -o prog
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$here/build}
mkdir -p "$out"
cc="${CC:-gcc} -O2 -fwrapv -I $here"

"$here/../bin/silly" build "$here/sillyc.silly" -o "$out/sillyc1"
"$out/sillyc1" "$here/sillyc.silly" "$out/stage2.c"
$cc "$out/stage2.c" -o "$out/sillyc2"
"$out/sillyc2" "$here/sillyc.silly" "$out/stage3.c"
if cmp -s "$out/stage2.c" "$out/stage3.c"; then
    cp "$out/sillyc2" "$out/sillyc"
    echo "bootstrap ok: $out/sillyc reproduces itself ($(wc -l < "$out/stage2.c") lines of C)"
else
    echo "bootstrap FAILED: stage2.c and stage3.c differ" >&2
    exit 1
fi
