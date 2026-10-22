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


def required_packages(path,preparation=False):
    required=pins(path)
    if preparation:required.update(pins(HERE/'requirements-dc-preparation.txt'))
    return required


def preparation_smoke():
    """Exercise installed compiled AMG operations, not merely package metadata."""
    import numpy as np
    import pyamg
    from scipy.sparse import diags
    size=256;matrix=diags([-np.ones(size-1),2*np.ones(size),-np.ones(size-1)],[-1,0,1],format='csr')
    right=np.ones(size);solver=pyamg.smoothed_aggregation_solver(matrix,symmetry='symmetric',coarse_solver='pinv',max_coarse=64)
    answer=solver.solve(right,tol=1e-12,maxiter=100,accel='cg')
    residual=float(np.linalg.norm(matrix@answer-right)/np.linalg.norm(right))
    if not np.isfinite(residual) or residual>1e-9:raise ValueError('Installed AMG original-equation residual exceeds 1e-9')
    return dict(status='passed-installed-amg-smoke-only',version=pyamg.__version__,size=size,relative_equation_residual=residual,
        scope='Installed numerical extension and original-equation residual check; not a physical source or force qualification')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requirements', type=Path, default=HERE/'requirements-dc-worker.txt')
    parser.add_argument('--preparation',action='store_true',help='Also require pinned source-preparation dependencies and exercise installed AMG operations')
    args = parser.parse_args()
    found = problems(required_packages(args.requirements,args.preparation));preparation=None
    if not found:
        sys.path.insert(0, str(HERE))
        try:
            import recalculate_dc_request, finite_current_coupling, desktop_dc_job, dc_applicability  # noqa: F401
            import ngsolve
            if args.preparation:
                import solve_linear_dc_study, prepare_linear_dc_copper  # noqa: F401
                import dc_preparation, prepare_dc_request, desktop_dc_preparation  # noqa: F401
                preparation=preparation_smoke()
        except Exception as error:
            found.append(f'live worker modules do not import: {error}')
    report = dict(status='rejected-dc-worker-environment' if found else 'passed-pinned-dc-worker-environment',
                  python=sys.executable, version=sys.version.split()[0], problems=found,
                  environment_scope='source-and-magnetic-worker' if args.preparation else 'magnetic-worker-only',preparation_smoke=preparation)
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if found else 0)


if __name__ == '__main__':
    main()
