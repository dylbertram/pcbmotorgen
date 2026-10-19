#!/usr/bin/env bash
# Install FEMM 4.2 (x64, 22 Oct 2023 build) under ~/.local/opt without root.
#
# Route: Debian bookworm debs (wine64 8.0, xvfb, innoextract, cabextract)
# fetched with a user-owned apt state and unpacked with `dpkg -x`. The FEMM
# Inno Setup installer is unpacked with innoextract (it is a 32-bit PE and
# wine64 alone cannot run it). The VC++ 2008 x64 runtime (mfc90, msvcr90,
# msvcp90) comes from the vcredist bundled in that installer and is copied next
# to femm.exe. Re-running is safe; finished steps are skipped.
set -euo pipefail
. /etc/os-release
[[ ${VERSION_CODENAME:-} == bookworm && $(uname -m) == x86_64 ]] || {
    echo 'This user-prefix Wine/FEMM installer requires Debian 12 x86_64.' >&2; exit 1;
}
for tool in apt-get dpkg cc curl sha256sum; do
    command -v "$tool" >/dev/null || { echo "Required host tool not found: $tool" >&2; exit 1; }
done

OPT=${FEMM_OPT:-$HOME/.local/opt}
APT_DIR=$OPT/apt
WINE_ROOT=$OPT/wine-root
TOOLS_ROOT=$OPT/femm-tools-root
FEMM_DIR=$OPT/femm
URL='https://www.femm.info/doku/lib/exe/fetch.php?media=upload:newbuild:femm42bin_x64_22oct2023.exe'
SHA256=fdc5047d2fccc4d759df2a82c4627e46408250c57967773fb5bd59cd9eb17253
HERE=$(cd "$(dirname "$0")" && pwd)

mkdir -p "$APT_DIR"/{state,lists/partial,cache/archives/partial} "$FEMM_DIR"
cat > "$APT_DIR/apt.conf" <<EOF
Dir::State "$APT_DIR/state";
Dir::State::Lists "$APT_DIR/lists";
Dir::State::status "/var/lib/dpkg/status";
Dir::Cache "$APT_DIR/cache";
APT::Sandbox::User "$(id -un)";
Debug::NoLocking "true";
EOF
export APT_CONFIG=$APT_DIR/apt.conf

# Download a package set (plus whatever the host lacks) and unpack it into $2.
fetch_debs() {
    local root=$1; shift
    local deb_dir=$APT_DIR/debs-$(basename "$root")
    mkdir -p "$deb_dir" "$root"
    local pkgs=() simulation
    # Include requested packages even when apt considers them installed on the
    # host: this private prefix still needs their executable/library files.
    simulation=$(apt-get -s install --no-install-recommends "$@")
    mapfile -t pkgs < <({ printf '%s\n' "$@"; awk '/^Inst/ {print $2}' <<< "$simulation"; } | sort -u)
    (cd "$deb_dir" && apt-get download "${pkgs[@]}" >/dev/null)
    for f in "$deb_dir"/*.deb; do dpkg -x "$f" "$root"; done
    (cd "$deb_dir" && sha256sum ./*.deb > sha256.txt)
}

if [ ! -x "$WINE_ROOT/usr/lib/wine/wine64" ]; then
    apt-get update >/dev/null 2>&1 || true
    fetch_debs "$WINE_ROOT" wine64 wine libwine xvfb xauth x11-xkb-utils
    # Debian's wineserver is a wrapper that hard-codes /usr/lib/wine.
    mv "$WINE_ROOT/usr/lib/wine/wineserver" "$WINE_ROOT/usr/lib/wine/wineserver.debian-wrapper"
    ln -s wineserver64 "$WINE_ROOT/usr/lib/wine/wineserver"
fi
if ! command -v xdpyinfo >/dev/null && [ ! -x "$WINE_ROOT/usr/bin/xdpyinfo" ]; then
    fetch_debs "$WINE_ROOT" x11-utils
fi
if [ ! -x "$TOOLS_ROOT/usr/bin/innoextract" ]; then
    apt-get update >/dev/null 2>&1 || true
    fetch_debs "$TOOLS_ROOT" innoextract cabextract
fi

# Xvfb runs xkbcomp from a compiled-in /usr/bin; this shim redirects it.
mkdir -p "$OPT/xvfb"
if [ ! -f "$OPT/xvfb/xkbbin.so" ]; then
    cc -shared -fPIC -O2 -o "$OPT/xvfb/xkbbin.so" "$HERE/xkbbin.c"
fi

cp "$HERE/femm_env.sh" "$FEMM_DIR/env.sh"
# shellcheck source=femm_env.sh
. "$FEMM_DIR/env.sh"

tools() { LD_LIBRARY_PATH=$TOOLS_ROOT/usr/lib/x86_64-linux-gnu "$TOOLS_ROOT/usr/bin/$1" "${@:2}"; }

EXE=$FEMM_DIR/dl/femm42bin_x64_22oct2023.exe
if [ ! -f "$EXE" ]; then
    mkdir -p "$FEMM_DIR/dl"
    curl -fsSL -o "$EXE" "$URL"
fi
echo "$SHA256  $EXE" | sha256sum -c --quiet

if [ ! -f "$WINEPREFIX/drive_c/femm42/bin/femm.exe" ]; then
    femm_xvfb
    # wineboot exits non-zero because there is no 32-bit (syswow64) side.
    wine64 wineboot -i >/dev/null 2>&1 || true
    wineserver -w
    # user32 imports zlib1.dll; WINEDLLPATH alone does not cover every lookup.
    cp "$WINE_ROOT/usr/x86_64-w64-mingw32/lib/zlib1.dll" "$WINEPREFIX/drive_c/windows/system32/"

    rm -rf "$FEMM_DIR/app-extract" "$FEMM_DIR/vcredist"
    mkdir -p "$FEMM_DIR/app-extract" "$FEMM_DIR/vcredist/x"
    (cd "$FEMM_DIR/app-extract" && tools innoextract -s "$EXE")
    (cd "$FEMM_DIR/vcredist" && tools cabextract -q "$FEMM_DIR/app-extract/tmp/vcredist_x64.exe" \
        && tools cabextract -q -d x vc_red.cab)

    D=$WINEPREFIX/drive_c/femm42
    cp -r "$FEMM_DIR/app-extract/app" "$D"
    for n in mfc90 mfc90u mfc90enu msvcr90 msvcp90; do
        f=$(ls "$FEMM_DIR/vcredist/x" | grep "^$n\.dll\..*x64" | head -1)
        cp "$FEMM_DIR/vcredist/x/$f" "$D/bin/$n.dll"
    done
fi
echo "FEMM installed in $WINEPREFIX/drive_c/femm42"
