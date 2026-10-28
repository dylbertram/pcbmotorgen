#!/usr/bin/env bash
# Native serial Elmer reference build. Requires a user-installed Fortran compiler.
set -euo pipefail
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || { echo 'Requires native Apple Silicon macOS' >&2; exit 1; }
OPT=${SOLVER_OPT:-$HOME/.local/opt/solver-prototypes-macos}
FORTRAN=${FC:-$(command -v gfortran || true)}
[[ -n "$FORTRAN" && -x "$FORTRAN" ]] || { echo 'Install gfortran first, or set FC to its absolute path.' >&2; exit 1; }
for tool in cmake curl tar shasum; do command -v "$tool" >/dev/null; done
mkdir -p "$OPT/downloads"
OPT=$(cd "$OPT" && pwd)
ARCHIVE=elmerfem-release-26.2.tar.gz
SHA=7addfb102d735929a40929be08be0c16703d734498d33bc70c96e7d526fe249c
if [[ ! -f "$OPT/downloads/$ARCHIVE" ]]; then
    curl -fL --max-time 600 "https://github.com/ElmerCSC/elmerfem/releases/download/release-26.2/$ARCHIVE" -o "$OPT/downloads/$ARCHIVE.part"
    mv "$OPT/downloads/$ARCHIVE.part" "$OPT/downloads/$ARCHIVE"
fi
echo "$SHA  $OPT/downloads/$ARCHIVE" | shasum -a 256 -c -
if [[ ! -d "$OPT/elmerfem-release-26.2" ]]; then
    tar -xzf "$OPT/downloads/$ARCHIVE" -C "$OPT"
fi
# Retain the default bundled UMFPACK: in this release WITH_UMFPACK=OFF
# still adds its library names to the link line, without building them.
cmake -S "$OPT/elmerfem-release-26.2" -B "$OPT/elmer-build" \
    -DCMAKE_INSTALL_PREFIX="$OPT/elmer-install" -DCMAKE_Fortran_COMPILER="$FORTRAN" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DWITH_MPI=OFF -DWITH_OpenMP=OFF -DWITH_ELMERGUI=OFF -DWITH_ElmerIce=OFF \
    -DWITH_UMFPACK=ON -DEXTERNAL_UMFPACK=OFF \
    '-DINCLUDE_ELMER_MODULES=MagnetoDynamics;MagnetoDynamics2D;ResultOutputSolve;SaveData;StatMagSolve;StatCurrentSolve'
cmake --build "$OPT/elmer-build" -j "${SOLVER_BUILD_JOBS:-4}"
cmake --install "$OPT/elmer-build"
{
    printf 'export ELMER_SOLVER=%q\n' "$OPT/elmer-install/bin/ElmerSolver"
    printf 'export ELMER_GRID=%q\n' "$OPT/elmer-install/bin/ElmerGrid"
} > "$OPT/env-elmer.sh"
{
    "$FORTRAN" --version
    cmake --version
    shasum -a 256 "$OPT/elmer-install/bin/ElmerSolver" "$OPT/elmer-install/bin/ElmerGrid"
    otool -L "$OPT/elmer-install/bin/ElmerSolver"
} > "$OPT/elmer-toolchain.txt"
echo "Elmer reference tools built. Source $OPT/env-elmer.sh. Run upstream and free-space gates before finite jobs."
echo 'No app bundling or physics qualification is implied. Review Elmer, bundled UMFPACK and compiler/dependency licenses before redistribution.'
