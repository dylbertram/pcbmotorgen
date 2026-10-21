#!/usr/bin/env bash
# Native Apple Silicon diagnostic tools. No sudo or Docker required.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || { echo 'Requires native Apple Silicon macOS' >&2; exit 1; }
SOLVER_OPT=${SOLVER_OPT:-$HOME/.local/opt/solver-prototypes-macos}
VENV=${VENV:-$ROOT/.magpy-venv}
mkdir -p "$SOLVER_OPT/downloads" "$SOLVER_OPT/bin"
SOLVER_OPT=$(cd "$SOLVER_OPT" && pwd)
ARCHIVE=getdp-4.0.0-MacOSARMc.tgz
SHA=6fe77e17aac2ec29aefd12e70db80fd54033016d55ed3e2c4c1e1470afd27b2f
if [[ ! -f "$SOLVER_OPT/downloads/$ARCHIVE" ]]; then
    curl -fL "https://getdp.info/bin/macOS/$ARCHIVE" -o "$SOLVER_OPT/downloads/$ARCHIVE.part"
    mv "$SOLVER_OPT/downloads/$ARCHIVE.part" "$SOLVER_OPT/downloads/$ARCHIVE"
fi
echo "$SHA  $SOLVER_OPT/downloads/$ARCHIVE" | shasum -a 256 -c -
if [[ ! -d "$SOLVER_OPT/getdp-4.0.0-MacOSARM" ]]; then
    tar -xzf "$SOLVER_OPT/downloads/$ARCHIVE" -C "$SOLVER_OPT"
fi
bash "$HERE/bootstrap_python.sh" "$VENV"
VENV=$(cd "$VENV" && pwd)
"$VENV/bin/python" -m pip install gmsh==4.13.1
# The wheel's gmsh script uses /usr/bin/env python. Invoke its own interpreter
# explicitly so another pyenv/system installation cannot silently replace it.
{
    echo '#!/usr/bin/env bash'
    printf 'exec %q %q "$@"\n' "$VENV/bin/python" "$VENV/bin/gmsh"
} > "$SOLVER_OPT/bin/gmsh"
chmod +x "$SOLVER_OPT/bin/gmsh"
{
    printf 'export SOLVER_OPT=%q\n' "$SOLVER_OPT"
    printf 'export SOLVER_PYTHON=%q\n' "$VENV/bin/python"
    printf 'export GMSH=%q\n' "$SOLVER_OPT/bin/gmsh"
    printf 'export GETDP=%q\n' "$SOLVER_OPT/getdp-4.0.0-MacOSARM/bin/getdp"
    echo 'export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}" OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}" VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"'
    echo 'export PCB_MOTOR_SOLVER_THREADS="${PCB_MOTOR_SOLVER_THREADS:-1}"'
} > "$SOLVER_OPT/env.sh"
"$SOLVER_OPT/bin/gmsh" -version
"$SOLVER_OPT/getdp-4.0.0-MacOSARM/bin/getdp" -info
"$VENV/bin/python" -m pip freeze > "$SOLVER_OPT/python-packages.txt"
echo "Source $SOLVER_OPT/env.sh before running diagnostics. Free-space and finite-force gates still apply."
