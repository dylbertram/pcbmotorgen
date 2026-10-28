#!/usr/bin/env python3
"""Compare finite RT0 source fields at explicit approved-material pilot points.

Analytical cell-face Green integration is compared with separately refined
tetrahedron volume quadrature. Shares the exported physical current source;
this is an integration check, not an independent magnetic/current solve or
qualification of all material quadrature points, force, saturation or hardware.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_tetra_current_field import tetrahedron_field
from post_project_force import sha
from source_snapshot import capture


def volume_field(points, cells, mean, slope, rule, batch_cells=2048):
    local = np.array([ip.point[:3] for ip in rule])
    weights = np.array([ip.weight for ip in rule])
    result = np.zeros_like(points)
    for begin in range(0, len(cells), batch_cells):
        part = cells[begin:begin+batch_cells]
        matrix = part[:, 1:]-part[:, :1]
        determinant = abs(np.linalg.det(matrix))
        positions = part[:, :1]+np.einsum('qi,cij->cqj', local, matrix)
        density = mean[begin:begin+len(part), None, :]+slope[begin:begin+len(part), None, None]*(positions-part.mean(axis=1)[:, None, :])
        weighted = (density*(determinant[:, None]*weights[None, :])[:, :, None]).reshape(-1, 3)
        positions = positions.reshape(-1, 3)
        for i, point in enumerate(points):
            difference = point-positions
            radius2 = np.einsum('ni,ni->n', difference, difference)
            if np.any(radius2 <= 0):
                raise ValueError('Singular volume-current observation; no softened radius')
            result[i] += 1e-7*np.sum(np.cross(weighted, difference)/radius2[:, None]**1.5, axis=0)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work', type=Path, required=True)
    parser.add_argument('--material-work', type=Path, required=True)
    parser.add_argument('--section-audit', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--orders', type=int, nargs='+', default=[2, 4, 6])
    args = parser.parse_args()
    if len(args.orders) < 2 or any(n not in [2, 4, 6, 8, 10, 12] for n in args.orders) or any(a >= b for a, b in zip(args.orders, args.orders[1:])):
        parser.error('At least two increasing supported volume quadrature orders required')
    origin, material_work, section_path, work = [p.resolve() for p in
        [args.source_work, args.material_work, args.section_audit, args.work]]
    if work.exists():
        parser.error('Preserve previous source-field pilots')
    source = json.loads((origin/'summary.json').read_text())
    material = json.loads((material_work/'summary.json').read_text())
    sections = json.loads(section_path.read_text())
    for entry in [source, material, sections]:
        completed_receipt(entry)
    if source['status'] != 'passed-affine-rt0-source-export-only' or material['status'] != 'completed-approved-disjoint-material-geometry-only' or material['failures']:
        raise ValueError('Unaccepted source or material geometry')
    if sections['status'] != 'passed-finite-dc-all-eligible-winding-sections-only' or sections['failures'] or len(sections['sections']) != sections['expected_sections']:
        raise ValueError('Need the whole expanded source-section audit')
    if source['source_work'] != material['current_source_work'] or sections['source_work'] != source['source_work']:
        raise ValueError('Geometry/source/sections refer to different physical current sources')
    if sections['source_summary_sha256'] != source['input_hashes'][str(Path(source['source_work'])/'summary.json')]:
        raise ValueError('Section audit and source export use different saved current states')
    archive_path = origin/'rt0-source.npz'
    inputs = {str(origin/'summary.json'): sha(origin/'summary.json'), str(archive_path): source['archive_sha256'],
              str(material_work/'summary.json'): sha(material_work/'summary.json'), str(section_path): sha(section_path),
              **source['input_hashes'], **material['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Physical source input changed: '+path)
    soft = [r for r in material['model']['stack'] if r['mu_r'] > 1]
    if len(soft) != 1:
        raise ValueError('Pilot currently requires one explicit magnetic envelope')
    region = soft[0]
    low = np.asarray(region['origin_m'])
    high = low+region['size_m']
    traces = [p for p in sections['sections'] if p['label'].startswith('trace:')]
    lowest = min(p['centre_m'][2] for p in traces)
    eligible = [p for p in traces if abs(p['centre_m'][2]-lowest) < 1e-12 and
                np.all(np.asarray(p['centre_m'][:2]) > low[:2]) and np.all(np.asarray(p['centre_m'][:2]) < high[:2])]
    eligible.sort(key=lambda p: (p['centre_m'][0], p['label']))
    if not eligible:
        raise ValueError('No deterministic lower-copper trace probes below the actual ferrite')
    selected = [eligible[i] for i in np.unique(np.linspace(0, len(eligible)-1, min(3, len(eligible)), dtype=int))]
    points = np.array([[p['centre_m'][0], p['centre_m'][1], z] for z in [high[2], (low[2]+high[2])/2] for p in selected])
    with np.load(archive_path, allow_pickle=False) as archive:
        cells = archive['vertices_m'][archive['cells']]
        mean, slope = archive['mean_current_a_m2'], archive['radial_slope_a_m3']
    import ngsolve as ng
    if ng.__version__ != source['version']:
        raise ValueError('Source quadrature engine changed')
    work.mkdir(parents=True)
    report = {'status': 'running', 'scope': __doc__, 'input_hashes': inputs,
              'points_m': points.tolist(), 'selected_physical_trace_labels': [p['label'] for p in selected],
              'point_selection': 'Deterministic first/middle/last lower-trace centre within ferrite footprint, projected to top and mid-depth; not selected by FE error.',
              'basis': 'Saved1V source, not prescribed1A; per-loop-current normalization is reported explicitly.',
              'effective_loop_current_a': source['effective_loop_current_a'], 'levels': {}, 'failures': [],
              'volume_quadrature_orders': args.orders,
              'relative_refinement_limit': .02, 'relative_agreement_limit': .05, 'field_floor_t': 1e-12,
              'source_snapshots': capture(work, [Path(__file__), Path(__file__).with_name('finite_tetra_current_field.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    started = time.monotonic()
    save()
    try:
        now = time.monotonic()
        exact = tetrahedron_field(points, cells, mean, radial_slope=slope)
        report['analytical_field_t'] = exact.tolist()
        report['analytical_seconds'] = time.monotonic()-now
        save()
        print('Analytical finite-cell field completed', report['analytical_seconds'], flush=True)
        for order in args.orders:
            now = time.monotonic()
            field = volume_field(points, cells, mean, slope, ng.IntegrationRule(ng.ET.TET, order))
            report['levels'][str(order)] = {'field_t': field.tolist(), 'seconds': time.monotonic()-now}
            save()
            print('Volume quadrature', order, 'seconds', time.monotonic()-now, flush=True)
        first, fine = [np.asarray(report['levels'][str(n)]['field_t']) for n in args.orders[-2:]]
        scale = np.maximum(np.linalg.norm(fine, axis=1), report['field_floor_t'])
        refinement = np.linalg.norm(first-fine, axis=1)/scale
        agreement = np.linalg.norm(exact-fine, axis=1)/scale
        report.update(refinement_relative=refinement.tolist(), agreement_relative=agreement.tolist(),
                      analytical_field_t_per_loop_a=(exact/source['effective_loop_current_a']).tolist())
        if np.max(refinement) > .02:
            report['failures'].append('Volume-source quadrature'+str(args.orders[-2:])+' exceeds unchanged2%gate')
        if np.max(agreement) > .05:
            report['failures'].append('Analytical/volume integration exceeds unchanged5%gate')
        for path, digest in inputs.items():
            if sha(Path(path)) != digest:
                raise ValueError('Source changed during pilot')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']:
                raise ValueError('Field implementation changed during pilot')
        report.update(status=('failed' if report['failures'] else 'passed')+'-recorded-material-source-points-only', seconds=time.monotonic()-started)
        save()
        if report['failures']:
            raise ValueError('; '.join(report['failures']))
    except BaseException as error:
        report.update(status='failed-recorded-material-source-points-only', error=str(error), seconds=time.monotonic()-started)
        save()
        raise


if __name__ == '__main__':
    main()
