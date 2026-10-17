# Environment for the user-prefix Wine + Xvfb used to run FEMM. Source it.
OPT=${FEMM_OPT:-$HOME/.local/opt}
R=$OPT/wine-root
export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export PATH=$R/usr/lib/wine:$R/usr/bin:$PATH
export WINESERVER=$R/usr/lib/wine/wineserver64
export WINELOADER=$R/usr/lib/wine/wine64
export WINEDLLPATH=$R/usr/x86_64-w64-mingw32/lib
export WINEPREFIX=$OPT/femm/prefix
export WINEARCH=win64
export WINEDEBUG=${WINEDEBUG:--all}
export WINEDLLOVERRIDES="mscoree,mshtml="

# Start Xvfb on $1 (default :77) unless it is already up, and export DISPLAY.
femm_xvfb() {
    local d=${1:-${FEMM_DISPLAY:-:77}}
    if [ ! -S "/tmp/.X11-unix/X${d#:}" ]; then
        env XKB_BIN_DIR="$R/usr/bin" LD_PRELOAD="$OPT/xvfb/xkbbin.so" \
            "$R/usr/bin/Xvfb" "$d" -nolisten tcp -screen 0 1280x1024x24 >/dev/null 2>&1 &
        for _ in $(seq 50); do [ -S "/tmp/.X11-unix/X${d#:}" ] && break; sleep 0.1; done
    fi
    export DISPLAY=$d
}
