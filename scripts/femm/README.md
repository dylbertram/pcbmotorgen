# FEMM 4.2 check of the backplane model (t707)

Offline 2-D finite-element check of `crates/pcbmotorgen-simulation/src/backplane`.
Magpylib cannot model soft magnetic material, so this uses FEMM 4.2. Results
and discussion are in [RESULTS.md](RESULTS.md).

## Running FEMM on Linux without root

FEMM only ships for Windows. It runs here under Wine 8.0 (wine64 only) with a
user-prefix Xvfb. Everything goes under `~/.local/opt` (`FEMM_OPT` overrides).

```sh
scripts/femm/install_femm.sh                 # once; about 130 MB of downloads
scripts/femm/run_femm.sh scripts/femm/smoke_wire.lua ~/.local/opt/femm-runs/smoke
cat ~/.local/opt/femm-runs/smoke/smoke_wire.csv
python3 -I scripts/femm/femm_backplane.py    # full comparison
python3 -I scripts/femm/femm_backplane.py --new-only   # saturation and eddy-current part only
python3 scripts/femm/check_convergence.py --work ~/.local/opt/femm-runs/convergence
```

What `install_femm.sh` does, and why:

| Step | Detail |
|---|---|
| Debian debs without root | `apt-get` with a user-owned `Dir::State`, `Dir::Cache`, `APT::Sandbox::User` and `Debug::NoLocking`, then `apt-get download` + `dpkg -x` for `wine64 wine xvfb xauth` (and `innoextract cabextract`) plus whatever the host lacks. |
| wineserver | Debian's `/usr/lib/wine/wineserver` is a shell wrapper with a hard-coded path. It is replaced by a symlink to `wineserver64` in the extracted copy. |
| zlib1.dll | Wine's `user32.dll` imports `zlib1.dll` from `libz-mingw-w64`. Set `WINEDLLPATH`, and also copy it into the prefix's `system32`, because `WINEDLLPATH` is not used for every lookup. |
| Xvfb keymap | Xvfb runs `xkbcomp` from a compiled-in `/usr/bin`. `xkbbin.c` is an `LD_PRELOAD` shim that points `XkbBinDirectory` at `$XKB_BIN_DIR`. Without a display, FEMM's windows fail with `nodrv_CreateWindow`. |
| FEMM installer | `femm42bin_x64_22oct2023.exe` is a 32-bit Inno Setup stub that wine64 cannot run. `innoextract` unpacks it (the SHA-256 is pinned in the script). |
| VC++ 2008 runtime | `femm.exe` needs `mfc90`, `msvcr90` and `msvcp90` (x64). They come from the `vcredist_x64.exe` inside the installer, unpacked with `cabextract` and copied next to `femm.exe`. |

`run_femm.sh <script.lua> [args...]` sources `femm_env.sh`, starts Xvfb on
`:77` (`FEMM_DISPLAY`) if needed, and runs

```sh
wine64 C:\femm42\bin\femm.exe -lua-script=<wrapper> -lua-var=arg1=<..> ... -windowhide
```

Arguments arrive in Lua as `arg1`, `arg2`, ...; existing paths are converted to
`Z:\...`. The wrapper sets `_ERRORMESSAGE` so a Lua error is printed and the
run exits 1 instead of opening a modal dialog. Dialogs that FEMM raises outside
Lua (for example "Material properties have not been defined for all regions")
still block. `FEMM_TIMEOUT` (default 300 s) ends such runs. To read the
dialog text, use `WINEDEBUG=+msgbox`.

Jobs lock their Wine prefix, so two runs cannot interfere with the same FEMM
windows. On failure or timeout, cleanup matches the exact output directory and
Wine prefix before killing orphan `fkn.exe`/`triangle.exe` workers. It does not
kill unrelated Wine applications. Unit tests cover that scope.

For solver progress in the headless Xvfb display, pass `show` as the third Lua
argument and omit the main-window hiding option:

```sh
FEMM_WINDOWHIDE='' scripts/femm/run_femm.sh scripts/femm/solve_case.lua \
  /absolute/path/to/case.lua /absolute/path/to/output show
```

The failed extra-fine thin-sheet job was inspected this way. It remained in
node renumbering, not an accepted field solve, and timed out even at 1200 s.
The convergence harness now refines material/gap mesh and far-air mesh
independently. `--far-air-mesh` fixes the explicit far-air size during near-mesh
and domain refinement; an extra `airhalf` run separately checks its halving.
This avoids quartering all 80 mm of remote air merely to refine a 0.2 mm sheet.
The 2% gates remain unchanged. `--case thin thick pwm drag` selects cases;
`--mesh-scale 0.5` starts the local refinement one level finer.

Notes for writing FEMM Lua: it is Lua 4.0, built with radians (`sin`, `cos`
take radians). The post-processor call is `mo_getpointvalues`; `mo_getb` is
only an Octave/Matlab wrapper.

## Smoke test

`smoke_wire.lua` models a 1 mm-radius wire carrying 10 A inside an A = 0 circle,
and compares |B| at r = 5, 10, 20 and 40 mm (mean of 8 angles) with μ0·I/(2πr).
The errors are −0.80 %, +0.12 %, −0.02 % and +0.04 %. The far-field mesh is
FEMM's automatic one.

## Harness

| File | Role |
|---|---|
| `solve_case.lua` | Generic planar case: one electrical period with periodic left and right edges, A = 0 40 mm above and below, horizontal material bands, and embedded rectangles. Materials can be nonlinear (B-H points) and sources complex. Writes A·J over the sources, the weighted-stress-tensor force (x and y, time-averaged when harmonic) and resistive loss of the stack, the force on the magnets, the Bx and By fundamentals and the travelling-wave By part on sample lines, and point values. Magnetostatic, time-harmonic when `freq` > 0, or incremental on a previous nonlinear solution (`previous`). |
| `femm_backplane.py` | Builds the cases, runs FEMM and the Rust model, and prints the Markdown tables in RESULTS.md. Uses the stdlib only. |
| `../../crates/pcbmotorgen-simulation/examples/backplane_dump.rs` | Prints the model's `BackplaneAnalysis` for given stacks (JSON in and out). |
| `check_convergence.py` | Independently halves/quarters the near mesh, halves far-air mesh and extends the outer domain on thin/thick saturation, PWM screening and travelling-wave drag. Exits nonzero above 2% change or drag/Joule imbalance and writes `convergence.json`. A successful planar check is not 3D housing validation. |
# Display health

The runner checks an actual X connection with `xdpyinfo`, not only the presence
of `/tmp/.X11-unix/X77`. A dead Xvfb can leave that socket behind, and Wine can
then exit without solving or writing any output. A stale or inaccessible
configured display now fails explicitly. Select an unused display with
`FEMM_DISPLAY=:79` rather than deleting an unknown socket. `xdpyinfo` is required.
The failed dense-knee MnZn launch is retained separately from its fresh-display
retry; missing output is not physics evidence.
