#!/bin/bash
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
Xvfb -displayfd 1 -screen 0 1024x768x24 -nolisten tcp > "$scratch/display" &
server=$!
cleanup() {
    kill "$server" 2>/dev/null || :
    wait "$server" 2>/dev/null || :
    rm -f "$scratch/display"
    rmdir "$scratch"
}
trap cleanup EXIT
for i in {1..50}; do
    if [[ -s $scratch/display ]]; then break; fi
    sleep .04
done
[[ -s $scratch/display ]]
isolated=:$(cat "$scratch/display")
[[ $isolated != "${DISPLAY:-}" ]]
DISPLAY="$isolated" REIMS_DND_TEST_DISPLAY="$isolated" GDK_BACKEND=x11 NO_AT_BRIDGE=1 \
    /usr/bin/python3 "$here/test-x11.py"
