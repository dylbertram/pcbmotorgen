#!/usr/bin/env bash
# Run a FEMM 4.2 Lua script headless: scripts/femm/run_femm.sh <script.lua> [args...]
#
# Extra arguments reach the script as the globals arg1, arg2, ... (strings,
# set with FEMM's -lua-var). Arguments that are existing paths are converted
# to Wine's Z: form. FEMM shows Lua errors in a modal dialog, which would hang
# a headless run, so the script runs inside a wrapper that writes the error to
# stderr (via a file) and exits non-zero instead. quit() is called for you.
set -euo pipefail

[ $# -ge 1 ] || { echo "usage: $0 <script.lua> [args...]" >&2; exit 2; }
script=$(realpath "$1"); shift
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/femm_env.sh"
FEMM_BIN=$WINEPREFIX/drive_c/femm42/bin/femm.exe
[ -f "$FEMM_BIN" ] || { echo "FEMM not installed; run $HERE/install_femm.sh" >&2; exit 1; }
femm_xvfb

# Unix path -> Wine Z: drive path.
winpath() { local p; p=$(realpath "$1"); echo "Z:${p//\//\\}"; }

vars=()
i=1
for a in "$@"; do
    [ -e "$a" ] && a=$(winpath "$a")
    vars+=("-lua-var=arg$i=$a"); i=$((i + 1))
done

work=$(mktemp -d "$OPT/femm/run.XXXXXX")
trap 'rm -rf "$work"' EXIT
err=$work/error.txt
win_err=$(winpath "$work")\\error.txt
cat > "$work/wrap.lua" <<EOF
_ERRORMESSAGE = function(m)
  local h = openfile("${win_err//\\/\\\\}", "w")
  write(h, m, "\n")
  closefile(h)
  quit()
end
dofile("$(winpath "$script" | sed 's/\\/\\\\/g')")
quit()
EOF

cd "$(dirname "$script")"
timeout "${FEMM_TIMEOUT:-300}" wine64 "$FEMM_BIN" \
    "-lua-script=$(winpath "$work/wrap.lua")" "${vars[@]}" ${FEMM_WINDOWHIDE--windowhide}
if [ -s "$err" ]; then
    echo "FEMM Lua error in $script:" >&2
    cat "$err" >&2
    exit 1
fi
