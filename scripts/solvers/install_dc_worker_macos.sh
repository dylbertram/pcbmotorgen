#!/usr/bin/env bash
# Install the pinned static-DC worker into a NEW virtualenv. No sudo, no
# PYTHONPATH, no archive access. Usage: install_dc_worker_macos.sh VENV [PYTHON3.12]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
VENV=${1:?target virtualenv directory required}
PYTHON=${2:-python3.12}
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || { echo 'Requires native Apple Silicon macOS' >&2; exit 1; }
[[ ! -e "$VENV" ]] || { echo "Refusing to reuse existing $VENV" >&2; exit 1; }
"$PYTHON" -c 'import sys; assert sys.version_info[:2]==(3,12), sys.version' || { echo 'CPython 3.12 required' >&2; exit 1; }
"$PYTHON" -m venv "$VENV"
env -u PYTHONPATH "$VENV/bin/python" -m pip install --no-input --only-binary=:all: -r "$HERE/requirements-dc-worker.txt"
env -u PYTHONPATH "$VENV/bin/python" -m pip freeze > "$VENV/installed-dc-worker-packages.txt"
env -u PYTHONPATH "$VENV/bin/python" "$HERE/check_dc_worker.py"
echo "Set PCB_MOTOR_DC_PYTHON=$VENV/bin/python, PCB_MOTOR_DC_SOLVER_ROOT=$HERE and PCB_MOTOR_DC_ARCHIVE_ROOT to the qualified evidence archive."
