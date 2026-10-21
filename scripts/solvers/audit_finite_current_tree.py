#!/usr/bin/env python3
"""Opening-refinement/direct-reference pilot for the finite RT0 source tree.

No new current or magnetic solve. Uses the same immutable physical sources and
pilot points as the accepted direct cell/volume integration check. A passing
pilot is not full material-domain, force or coupled nonlinear qualification.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_current_tree import FiniteCurrentTree
from post_project_force import sha
from source_snapshot import capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work', type=Path, required=True)
    parser.add_argument('--direct-work', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--openings', type=float, nargs='+', default=[.3, .15, .075])
    parser.add_argument('--leaf-size', type=int, default=64)
    args = parser.parse_args()
    origin, direct_work, work = [p.resolve() for p in [args.source_work, args.direct_work, args.work]]
    if work.exists():
        parser.error('Preserve earlier hierarchy pilots')
    if len(args.openings) < 2 or any(not np.isfinite(x) or not 0 < x < 1 for x in args.openings) or any(a <= b for a, b in zip(args.openings, args.openings[1:])) or args.leaf_size < 1:
        parser.error('At least two decreasing opening ratios in(0,1) and positive leaf size required')
    source = json.loads((origin/'summary.json').read_text())
    direct = json.loads((direct_work/'summary.json').read_text())
    for entry in [source, direct]:
        completed_receipt(entry)
    if source['status'] != 'passed-affine-rt0-source-export-only' or direct['status'] != 'passed-recorded-material-source-points-only' or direct['failures']:
        raise ValueError('Unaccepted finite source or independent source integration pilot')
    if direct['input_hashes'].get(str(origin/'summary.json')) != sha(origin/'summary.json'):
        raise ValueError('Direct pilot and hierarchy use different source exports')
    archive_path = origin/'rt0-source.npz'
    inputs = {str(origin/'summary.json'): sha(origin/'summary.json'), str(archive_path): source['archive_sha256'],
              str(direct_work/'summary.json'): sha(direct_work/'summary.json'), **direct['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Immutable source/pilot input changed')
    with np.load(archive_path, allow_pickle=False) as archive:
        cells = archive['vertices_m'][archive['cells']]
        mean, slope = archive['mean_current_a_m2'], archive['radial_slope_a_m3']
    points = np.asarray(direct['points_m'])
    exact = np.asarray(direct['analytical_field_t'])
    reference = np.asarray(direct['levels'][str(direct['volume_quadrature_orders'][-1])]['field_t'])
    work.mkdir(parents=True)
    report = {'status': 'running', 'scope': __doc__, 'input_hashes': inputs, 'points_m': points.tolist(),
              'openings': args.openings, 'levels': {}, 'failures': [], 'field_floor_t': 1e-12,
              'source_snapshots': capture(work, [Path(__file__), Path(__file__).with_name('finite_current_tree.py'),
                                                Path(__file__).with_name('finite_tetra_current_field.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    started = time.monotonic()
    save()
    try:
        tree = FiniteCurrentTree(cells, mean, slope, leaf_size=args.leaf_size)
        report['tree'] = tree.metadata
        del cells, mean, slope
        for opening in args.openings:
            field = tree.field(points, opening)
            scale = np.maximum(np.linalg.norm(exact, axis=1), report['field_floor_t'])
            report['levels'][str(opening)] = dict(tree.last_evaluation, field_t=field.tolist(),
                direct_relative_difference=(np.linalg.norm(field-exact, axis=1)/scale).tolist(),
                volume_reference_relative_difference=(np.linalg.norm(field-reference, axis=1)/np.maximum(np.linalg.norm(reference, axis=1), report['field_floor_t'])).tolist())
            save()
            print('opening', opening, 'seconds', tree.last_evaluation['seconds'], 'max direct error', max(report['levels'][str(opening)]['direct_relative_difference']), flush=True)
        coarse, fine = [np.asarray(report['levels'][str(o)]['field_t']) for o in args.openings[-2:]]
        refinement = np.linalg.norm(coarse-fine, axis=1)/np.maximum(np.linalg.norm(fine, axis=1), report['field_floor_t'])
        report['opening_refinement_relative'] = refinement.tolist()
        if np.max(refinement) > .02:
            report['failures'].append('Opening refinement exceeds unchanged2%gate')
        last = report['levels'][str(args.openings[-1])]
        if max(last['direct_relative_difference']) > .05 or max(last['volume_reference_relative_difference']) > .05:
            report['failures'].append('Direct/volume reference agreement exceeds unchanged5%gate')
        for path, digest in inputs.items():
            if sha(Path(path)) != digest:
                raise ValueError('Physical source/pilot input changed during hierarchy evaluation')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']:
                raise ValueError('Hierarchy implementation changed during pilot')
        report.update(status=('failed' if report['failures'] else 'passed')+'-finite-source-tree-pilot-only', seconds=time.monotonic()-started)
        save()
        if report['failures']:
            raise ValueError('; '.join(report['failures']))
    except BaseException as error:
        report.update(status='failed-finite-source-tree-pilot-only', error=str(error), seconds=time.monotonic()-started)
        save()
        raise


if __name__ == '__main__':
    main()
