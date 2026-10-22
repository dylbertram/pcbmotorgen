#!/usr/bin/env python3
"""Reject a DC worker environment that differs from the pinned qualified one.

Checks platform, interpreter series and every pinned distribution version, then
imports the live worker modules. Exits nonzero with the exact mismatch; it never
installs, upgrades or substitutes packages, and solves nothing.
"""
import argparse
from importlib import metadata
import json
from pathlib import Path
import platform
import sys

HERE = Path(__file__).resolve().parent


def pins(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, version = line.split('==')
        result[name.lower().replace('_', '-')] = version
    return result


def problems(required, python=(3, 12)):
    found = []
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        found.append(f'platform {sys.platform}/{platform.machine()} is not the qualified macOS arm64 target')
    if sys.version_info[:2] != python:
        found.append(f'Python {sys.version_info[0]}.{sys.version_info[1]} differs from qualified {python[0]}.{python[1]}')
    for name, version in required.items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            found.append(f'missing {name}=={version}')
            continue
        if installed != version:
            found.append(f'{name} {installed} differs from pinned {version}')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requirements', type=Path, default=HERE/'requirements-dc-worker.txt')
    args = parser.parse_args()
    found = problems(pins(args.requirements))
    if not found:
        sys.path.insert(0, str(HERE))
        try:
            import recalculate_dc_request, finite_current_coupling, desktop_dc_job, dc_applicability  # noqa: F401
            import ngsolve
        except Exception as error:
            found.append(f'live worker modules do not import: {error}')
    report = dict(status='rejected-dc-worker-environment' if found else 'passed-pinned-dc-worker-environment',
                  python=sys.executable, version=sys.version.split()[0], problems=found)
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if found else 0)


if __name__ == '__main__':
    main()
