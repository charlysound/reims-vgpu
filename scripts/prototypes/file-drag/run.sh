#!/bin/bash
# Launch the experimental bridge against an already running Reims VM.
set -euo pipefail
if [[ $# -ne 1 ]]; then
    printf 'Usage: %s REIMS_X11_WINDOW_ID\n' "$0" >&2
    exit 2
fi
window=$1
here=$(cd -- "$(dirname -- "$0")" && pwd)
guest=${REIMS_DRAG_GUEST:?Set REIMS_DRAG_GUEST to an SSH destination}
port=${REIMS_DRAG_PORT:-22}
alias=${REIMS_DRAG_HOST_KEY_ALIAS:-}
domain=${REIMS_DRAG_DOMAIN:?Set REIMS_DRAG_DOMAIN to a libvirt domain name}
cache=${XDG_CACHE_HOME:-"$HOME/.cache"}/reims-file-drag
options=(-oBatchMode=yes -oStrictHostKeyChecking=yes -oConnectTimeout=4)
if [[ -n $alias ]]; then
    options+=("-oHostKeyAlias=$alias")
fi
ssh_guest=(ssh -T "${options[@]}" -p "$port" "$guest")
remote=$("${ssh_guest[@]}" '/usr/bin/mktemp -d /tmp/reims-file-drag.XXXXXXXX')
if [[ ! $remote =~ ^/tmp/reims-file-drag\.[a-zA-Z0-9]+$ ]]; then
    printf 'Unexpected guest workspace: %s\n' "$remote" >&2
    exit 1
fi
tag=${remote##*.}
label="local.reims.file-drag.$tag"
started=
cleanup() {
    if [[ -n $started ]]; then
        "${ssh_guest[@]}" "/bin/launchctl remove '$label'; /bin/rm -f '$remote/bridge.sock'" || :
    fi
    printf 'Transfer caches retained for pending copies: %s and %s (guest)\n' "$cache" "$remote" >&2
}
trap cleanup EXIT
scp -q "${options[@]}" -P "$port" "$here/guest.m" "$guest:$remote/guest.m"
"${ssh_guest[@]}" "/usr/bin/clang -Wall -Wextra -Werror -fobjc-arc -framework AppKit '$remote/guest.m' -o '$remote/guest' &&
    /bin/launchctl submit -l '$label' -- '$remote/guest' '$remote/guest.log' '$remote/bridge.sock'"
started=1
"${ssh_guest[@]}" "for attempt in {1..40}; do
  if test -S '$remote/bridge.sock'; then exit 0; fi
  /bin/sleep .1
done
cat '$remote/guest.log' >&2
exit 1"
/usr/bin/python3 "$here/bridge.py" --window "$window" --guest "$guest" --port "$port" \
    --host-key-alias "$alias" --libvirt-uri "${REIMS_DRAG_LIBVIRT_URI:-qemu:///session}" \
    --guest-dir "$remote" --cache "$cache" --domain "$domain"
