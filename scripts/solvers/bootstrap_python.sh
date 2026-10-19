#!/usr/bin/env bash
# Create a checkout-local numerical validation environment, without sudo.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
PYTHON=${PYTHON:-python3}
VENV=${1:-$ROOT/.magpy-venv}
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -r "$ROOT/scripts/requirements-validation.txt"
"$VENV/bin/python" -m pip check
echo "Validation Python ready: $VENV/bin/python"
