#!/usr/bin/env python3
"""Controlled finite-current values at every declared material quadrature point.

Preflight measures the actual source hierarchy on deterministic physical points
and checks tighter opening plus direct finite-cell references. Full mode repeats
opening refinement on ALL points before storing per-loop-ampere source values.
This is numerical source preparation, not nonlinear force/app qualification.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_current_quadrature import material_layout, source_components
from finite_current_tree import FiniteCurrentTree
from finite_current_zero_bias import magnetic_regions
from finite_tetra_current_field import tetrahedron_field
from post_project_force import sha
from source_snapshot import capture


def relative_difference(first, second, floor):
    first, second = np.asarray(first), np.asarray(second)
    if first.shape != second.shape or first.ndim != 2 or first.shape[1] != 3 or not all(np.isfinite(x).all() for x in [first, second]) or not np.isfinite(floor) or floor <= 0:
        raise ValueError('Matching field vectors and explicit positive numerical floor required')
    return np.linalg.norm(first-second, axis=1)/np.maximum(np.linalg.norm(second, axis=1), floor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work', type=Path, required=True)
    parser.add_argument('--mesh-work', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--preflight-work', type=Path)
    parser.add_argument('--degree', type=int, default=8)
    parser.add_argument('--openings', type=float, nargs='+', default=[.3, .15])
    parser.add_argument('--leaf-size', type=int, default=64)
    parser.add_argument('--preflight-points', type=int, default=256)
    parser.add_argument('--direct-points', type=int, default=64)
    parser.add_argument('--max-cache-seconds', type=float, default=900.)
    args = parser.parse_args()
    origin, mesh_work, work = [p.resolve() for p in [args.source_work, args.mesh_work, args.work]]
    if work.exists():
        parser.error('Preserve earlier source cache evidence')
    if args.degree < 2 or args.degree % 2 or min(args.leaf_size, args.preflight_points, args.direct_points) < 1 or not np.isfinite(args.max_cache_seconds) or args.max_cache_seconds <= 0:
        parser.error('Positive declared quadrature/resource controls required')
    if len(args.openings) < 2 or any(not np.isfinite(o) or not 0 < o < 1 for o in args.openings) or any(a <= b for a, b in zip(args.openings, args.openings[1:])):
        parser.error('At least two decreasing opening ratios required')
    source = json.loads((origin/'summary.json').read_text())
    mesh_source = json.loads((mesh_work/'summary.json').read_text())
    for entry in [source, mesh_source]:
        completed_receipt(entry)
    if source['status'] != 'passed-affine-rt0-source-export-only' or mesh_source['status'] not in ['passed-approved-material-mesh-controls-only', 'passed-recorded-zero-current-bias-controls-only']:
        raise ValueError('Unaccepted source export or approved material mesh')
    if mesh_source['input_hashes'].get(str(origin/'summary.json')) != sha(origin/'summary.json'):
        raise ValueError('Material mesh does not belong to the same finite current source')
    current = source['effective_loop_current_a']
    if not np.isfinite(current) or current <= 0:
        raise ValueError('Positive recorded source-loop current required for unit conversion')
    inputs = {str(origin/'summary.json'): sha(origin/'summary.json'), str(origin/'rt0-source.npz'): source['archive_sha256'],
              str(mesh_work/'summary.json'): sha(mesh_work/'summary.json'), str(mesh_work/'mesh.vol'): mesh_source['mesh_sha256'],
              **source['input_hashes'], **mesh_source['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Immutable physical source/mesh changed')
    request = {k: getattr(args, k) for k in ['degree', 'openings', 'leaf_size', 'preflight_points', 'direct_points']}
    if not args.preflight_only:
        if args.preflight_work is None:
            raise ValueError('A measured matching preflight is required before a full cache')
        prior_path = args.preflight_work.resolve()/'summary.json'
        prior = json.loads(prior_path.read_text())
        completed_receipt(prior)
        if prior['status'] != 'passed-finite-source-material-preflight-only' or prior['failures'] or prior['request'] != request:
            raise ValueError('Full cache needs a whole successful matching preflight')
        if any(prior['input_hashes'].get(path) != digest for path, digest in inputs.items()):
            raise ValueError('Preflight uses different source/mesh inputs')
        if prior['forecast_full_cache_seconds'] > args.max_cache_seconds:
            raise ValueError('Measured full-cache runtime forecast exceeds the declared budget')
        inputs[str(prior_path)] = sha(prior_path)
    import ngsolve as ng
    if ng.__version__ != source['version'] or ng.__version__ != mesh_source['version']:
        raise ValueError('Material/source engine changed')
    started = time.monotonic()
    mesh = ng.Mesh(str(mesh_work/'mesh.vol'))
    regions = '|'.join(r['name'] for r in magnetic_regions(mesh_source['model'], mesh.GetMaterials()))
    layout = material_layout(ng, mesh, regions, args.degree)
    selected = np.unique(np.linspace(0, len(layout.points)-1, min(args.preflight_points, len(layout.points)), dtype=int)) if args.preflight_only else np.arange(len(layout.points))
    points = layout.points[selected]
    direct_indices = np.unique(np.linspace(0, len(points)-1, min(args.direct_points, len(points)), dtype=int))
    with np.load(origin/'rt0-source.npz', allow_pickle=False) as archive:
        cells = archive['vertices_m'][archive['cells']]
        mean, slope = archive['mean_current_a_m2'], archive['radial_slope_a_m3']
    work.mkdir(parents=True)
    report = {'status': 'running', 'scope': __doc__, 'version': ng.__version__, 'input_hashes': inputs,
              'request': request, 'regions': regions, 'total_material_points': len(layout.points),
              'evaluated_points': len(points), 'direct_reference_points': len(direct_indices),
              'point_selection': 'Uniformly spaced deterministic indices in physical material quadrature order, not chosen by FE error.',
              'mesh_work': str(mesh_work), 'source_work': str(origin), 'model': mesh_source['model'],
              'unit': 'tesla per loop ampere, divided by the recorded1V-loop current without fitting',
              'field_floor_t_per_loop_a': 1e-12, 'levels': {}, 'failures': [],
              'source_snapshots': capture(work, [Path(__file__), *[Path(__file__).with_name(n) for n in
                  ['finite_current_tree.py', 'finite_tetra_current_field.py', 'finite_current_quadrature.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        tree = FiniteCurrentTree(cells, mean, slope, leaf_size=args.leaf_size)
        del cells, mean, slope
        report['tree'] = tree.metadata
        fields = []
        for opening in args.openings:
            field = tree.field(points, opening)/current
            fields.append(field)
            report['levels'][str(opening)] = tree.last_evaluation
            save()
            print('material points', len(points), 'opening', opening, 'seconds', tree.last_evaluation['seconds'], flush=True)
        change = relative_difference(fields[-2], fields[-1], report['field_floor_t_per_loop_a'])
        now = time.monotonic()
        direct = tetrahedron_field(points[direct_indices], tree.cells, tree.mean, radial_slope=tree.slope)/current
        direct_seconds = time.monotonic()-now
        agreement = relative_difference(fields[-1][direct_indices], direct, report['field_floor_t_per_loop_a'])
        report.update(maximum_pointwise_opening_relative_change=float(change.max()),
                      maximum_direct_reference_relative_difference=float(agreement.max()),
                      direct_reference_seconds=direct_seconds,
                      direct_reference_physical_points_m=points[direct_indices].tolist(),
                      direct_reference_field_t_per_loop_a=direct.tolist())
        if change.max() > .02:
            report['failures'].append('Material-point opening refinement exceeds unchanged2%gate')
        if agreement.max() > .05:
            report['failures'].append('Direct finite-cell reference exceeds unchanged5%gate')
        forecast = (sum(x['seconds'] for x in report['levels'].values())*len(layout.points)/len(points)
                    +tree.metadata['build_seconds']+direct_seconds)
        report['forecast_full_cache_seconds'] = forecast
        report['declared_cache_budget_seconds'] = args.max_cache_seconds
        report['full_cache_within_forecast_budget'] = forecast <= args.max_cache_seconds
        save()
        if not args.preflight_only and not report['failures']:
            # Preserve expensive numerical values before crossing the native
            # storage boundary. An archive alone is never an accepted cache.
            path = work/'material-current-source.npz'
            np.savez_compressed(path, points_m=layout.points, element_numbers=layout.element_numbers,
                                field_t_per_loop_a=fields[-1])
            report.update(cache_sha256=sha(path), checkpoint='unaccepted-fields-saved-before-native-storage-controls')
            save()
            _, _, storage = source_components(ng, mesh, layout, fields[-1])
            report.update(cache_sha256=sha(path), storage=storage)
        for path, digest in inputs.items():
            if sha(Path(path)) != digest:
                raise ValueError('Physical inputs changed during material source preparation')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']:
                raise ValueError('Source implementation changed during preparation')
        report.update(status=('failed' if report['failures'] else 'passed')+('-finite-source-material-preflight-only' if args.preflight_only else '-finite-source-material-quadrature-only'), seconds=time.monotonic()-started)
        save()
        if report['failures']:
            raise ValueError('; '.join(report['failures']))
    except BaseException as error:
        report.update(status='failed-finite-source-material-preparation', error=str(error), seconds=time.monotonic()-started)
        save()
        raise


if __name__ == '__main__':
    main()
