/* LD_PRELOAD shim: point Xvfb's compiled-in xkbcomp directory (/usr/bin) at
 * $XKB_BIN_DIR so a user-prefix Xvfb can compile its keymap. The symbol is weak
 * because the shim is inherited by the shell Xvfb spawns for xkbcomp. */
#include <stdlib.h>

extern char *XkbBinDirectory __attribute__((weak));

__attribute__((constructor)) static void set_xkb_bin(void) {
    char *d = getenv("XKB_BIN_DIR");
    if (d && &XkbBinDirectory)
        XkbBinDirectory = d;
}
