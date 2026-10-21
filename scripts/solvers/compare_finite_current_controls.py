#!/usr/bin/env python3
"""Compare accepted static reports without turning partial controls into release.

Checks total and zero-bias-subtracted force vectors using the same declared
1e-8 N near-zero floor and unchanged 2% refinement or 5% formulation gate.
An independent formulation shares physical prescribed sources, not FE unknowns.
Every input still needs its own force balance and nonlinear residual controls.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def forces(report):
    if report.get('failures'):
        raise ValueError('Failed reports cannot enter force comparisons')
    if report.get('status') == 'passed-recorded-zero-current-bias-controls-only':
        return {'0.0': np.asarray(report['states']['pm_zero_current_bias']['independent_pm_force_n'])}
    if report.get('status') == 'passed-recorded-finite-current-static-pilot-only':
        return {key: np.asarray(value['pm_array_force_n']) for key, value in report['states'].items()}
    raise ValueError('Incomplete or unsupported static force report')


def compare(first, second, kind):
    if kind not in ['refinement', 'formulation']:
        raise ValueError('Declare refinement or independent formulation')
    if first['model'] != second['model'] or first.get('material_control') != second.get('material_control'):
        raise ValueError('Material, physical geometry or PM pose differs')
    if kind == 'formulation' and {first.get('formulation', 'vector-b'), second.get('formulation', 'vector-b')} != {'vector-b', 'scalar-h'}:
        raise ValueError('Reference must use independent scalar-H and vector-B unknowns')
    a, b = forces(first), forces(second)
    if a.keys() != b.keys() or '0.0' not in a:
        raise ValueError('Zero/current state sets differ')
    output = {}
    gate = .02 if kind == 'refinement' else .05
    for key in a:
        for incremental in ([False] if key == '0.0' else [False, True]):
            x = a[key]-a['0.0'] if incremental else a[key]
            y = b[key]-b['0.0'] if incremental else b[key]
            if x.shape != (3,) or y.shape != (3,) or not np.isfinite([x, y]).all():
                raise ValueError('Finite physical force vectors required')
            difference = float(np.linalg.norm(x-y))
            limit = max(1e-8, gate*float(np.linalg.norm(y)))
            output[key+('-increment' if incremental else '-total')] = dict(difference_n=difference,
                limit_n=limit, relative_difference=difference/max(float(np.linalg.norm(y)), 1e-8), passed=difference <= limit)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--second', type=Path, required=True)
    parser.add_argument('--kind', choices=['refinement', 'formulation'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve existing comparisons')
    paths = [p.resolve() for p in [args.first, args.second]]
    reports = [json.loads(p.read_text()) for p in paths]
    inputs = {str(p): sha(p) for p in paths}
    for report, report_path in zip(reports, paths):
        if not report.get('command_receipt'):
            raise ValueError('A whole successful supervisor receipt is required')
        completed_receipt(report)
        for path, digest in report['input_hashes'].items():
            if sha(Path(path)) != digest:
                raise ValueError('Static physical input changed')
        if report.get('status') == 'passed-recorded-zero-current-bias-controls-only':
            if sha(report_path.parent/'mesh.vol') != report['mesh_sha256'] or sha(report_path.parent/'zero-current-reaction.sol') != report['states']['pm_zero_current_bias']['solution_sha256']:
                raise ValueError('Zero-current saved magnetic state changed')
        elif report.get('status') == 'passed-recorded-finite-current-static-pilot-only':
            for state in report['states'].values():
                if sha(report_path.parent/state['solution']) != state['solution_sha256']:
                    raise ValueError('Saved current-driven magnetic state changed')
        for path, entry in report['source_snapshots'].items():
            # Older accepted implementations may differ from current code.
            # Snapshot paths are relative to the report's work, not log folder.
            work = report_path.parent
            if sha(work/entry['snapshot']) != entry['sha256']:
                raise ValueError('Archived implementation snapshot changed')
    controls = compare(*reports, args.kind)
    passed = all(value['passed'] for value in controls.values())
    result = {'status': ('passed' if passed else 'failed')+'-recorded-force-'+args.kind+'-only',
              'scope': __doc__, 'input_hashes': inputs, 'kind': args.kind, 'force_floor_n': 1e-8,
              'controls': controls, 'source_snapshots': capture(args.output.parent/args.output.stem, [Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        result['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    if not passed:
        raise ValueError('Static force comparison exceeds unchanged gate')


if __name__ == '__main__':
    main()
