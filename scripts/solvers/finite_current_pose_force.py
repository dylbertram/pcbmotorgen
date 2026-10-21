#!/usr/bin/env python3
"""Bare PM/current force references at explicit poses from every affine RT0 cell.

Vectorized physical-volume quadrature retains mean J plus its radial RT0 term.
Independent PM-face and copper Lorentz kernels check action/reaction. This is
not a magnetic material solve, line-source model or new electrical current solve.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_current_zero_bias import posed_model
from pm_current_force import array_force
from post_project_force import sha
from reduced_potential import source_field
from source_snapshot import capture


def batches(cells, mean, slope, local, weights, batch_cells=4096):
    if batch_cells < 1 or cells.shape != (len(mean), 4, 3) or slope.shape != (len(mean),):
        raise ValueError('Matching affine finite cells/current data and positive batch size required')
    for start in range(0, len(cells), batch_cells):
        vertices = cells[start:start+batch_cells]
        matrix = vertices[:, 1:]-vertices[:, :1]
        determinant = abs(np.linalg.det(matrix))
        if np.any(determinant <= 0):
            raise ValueError('Degenerate physical source tetrahedron')
        points = vertices[:, :1]+np.einsum('qa,nab->nqb', local, matrix)
        values = (mean[start:start+batch_cells, None, :]+slope[start:start+batch_cells, None, None]*
                  (points-vertices.mean(axis=1)[:, None]))
        physical_weights = determinant[:, None]*weights[None, :]
        yield points.reshape(-1, 3), values.reshape(-1, 3), physical_weights.ravel()


def volume_errors(actual, archived_mesh, exact_cad):
    if not np.isfinite([actual, archived_mesh, exact_cad]).all() or min(actual, archived_mesh, exact_cad) <= 0:
        raise ValueError('Positive immutable mesh and CAD volume references required')
    return abs(actual/archived_mesh-1), abs(archived_mesh/exact_cad-1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work', type=Path, required=True)
    parser.add_argument('--material-work', type=Path, required=True)
    parser.add_argument('--bare-reference', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--preflight-work', type=Path)
    parser.add_argument('--max-seconds', type=float, default=1800.)
    args = parser.parse_args()
    origin, material_work, reference_path, work = [p.resolve() for p in
        [args.source_work, args.material_work, args.bare_reference, args.work]]
    if work.exists() or not np.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error('Fresh output directory and explicit positive runtime budget required')
    source = json.loads((origin/'summary.json').read_text())
    material = json.loads((material_work/'summary.json').read_text())
    reference = json.loads(reference_path.read_text())
    for entry in [source, material, reference]:
        if not entry.get('command_receipt'):
            raise ValueError('Whole successful source/material/reference receipts required')
        completed_receipt(entry)
    if source['status'] != 'passed-affine-rt0-source-export-only' or material['status'] != 'completed-approved-disjoint-material-geometry-only' or material['failures']:
        raise ValueError('Accepted actual source and approved material geometry required')
    if material['current_source_work'] != source['source_work'] or reference['source_work'] != source['source_work'] or reference['status'] != 'passed-bare-finite-dc-pm-force-only' or reference['failures']:
        raise ValueError('Unaccepted or mismatched original bare-current reference')
    current_work = Path(source['source_work'])
    if reference['source_summary_sha256'] != source['input_hashes'][str(current_work/'summary.json')] or reference['source_solution_sha256'] != source['input_hashes'][str(current_work/'dc-current-potential.sol')]:
        raise ValueError('Original reference has different current-source provenance')
    inputs = {str(origin/'summary.json'): sha(origin/'summary.json'), str(origin/'rt0-source.npz'): source['archive_sha256'],
              str(material_work/'summary.json'): sha(material_work/'summary.json'), str(reference_path): sha(reference_path),
              **source['input_hashes'], **material['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Immutable physical pose-force input changed')
    original = json.loads((current_work/'summary.json').read_text())
    model_path = next(Path(p) for p in original['input_hashes'] if Path(p).name == 'summary.json' and sha(Path(p)) == reference['model_summary_sha256'])
    if json.loads(model_path.read_text())['model']['magnets'] != material['model']['magnets']:
        raise ValueError('Original reference uses different PM geometry/nominal pose')
    inputs[str(model_path)] = reference['model_summary_sha256']
    offsets = [0., .0001, -.0001]
    if not args.preflight_only:
        if args.preflight_work is None:
            raise ValueError('Measured immutable matching preflight required')
        prior_path = args.preflight_work.resolve()/'summary.json'
        prior = json.loads(prior_path.read_text());completed_receipt(prior)
        if prior['status'] != 'completed-bare-pose-runtime-preflight-only' or prior['input_hashes'] != inputs or prior['forecast_seconds'] > args.max_seconds:
            raise ValueError('Preflight is unmatched, incomplete or exceeds the runtime allowance')
        inputs[str(prior_path)] = sha(prior_path)
    import ngsolve as ng
    if ng.__version__ != source['version']:
        raise ValueError('Pinned source quadrature engine changed')
    with np.load(origin/'rt0-source.npz', allow_pickle=False) as archive:
        cells = archive['vertices_m'][archive['cells']]
        mean, slope = archive['mean_current_a_m2'], archive['radial_slope_a_m3']
    count = len(cells)
    if args.preflight_only:
        indices = np.unique(np.linspace(0, count-1, min(1024, count), dtype=int))
        cells, mean, slope = cells[indices], mean[indices], slope[indices]
    work.mkdir(parents=True)
    report = dict(status='running', scope=__doc__, model=material['model'], source_work=str(origin),
                  input_hashes=inputs, poses={}, failures=[], offsets_x_m=offsets, cells_evaluated=len(cells),
                  source_cells=count, effective_loop_current_a=source['effective_loop_current_a'],
                  archived_mesh_volume_m3=original['geometric_volume_check']['mesh_volume_m3'],
                  exact_cad_volume_m3=source['original_current_geometry']['volume_m3'],
                  source_snapshots=capture(work, [Path(__file__), *[Path(__file__).with_name(n) for n in
                      ['pm_current_force.py', 'reduced_potential.py', 'finite_current_zero_bias.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    started = time.monotonic();save()
    try:
        for offset in offsets:
            model = posed_model(material['model'], offset)
            incident = source_field(model)
            levels = {}
            for degree in [2, 4]:
                rule = ng.IntegrationRule(ng.ET.TET, degree)
                local = np.array([point.point[:3] for point in rule])
                weights = np.array([point.weight for point in rule])
                pm, copper, net, volume, power = np.zeros(3), np.zeros(3), np.zeros(3), 0., 0.
                for points, values, physical_weights in batches(cells, mean, slope, local, weights):
                    weighted = values*physical_weights[:, None]
                    pm += array_force(model['magnets'], points, weighted).sum(axis=0)
                    copper += np.cross(weighted, incident(points)).sum(axis=0)
                    net += weighted.sum(axis=0)
                    volume += float(physical_weights.sum())
                    power += source['resistivity_ohm_m']*float(physical_weights@(values*values).sum(axis=1))
                balance = float(np.linalg.norm(pm+copper))
                levels[str(degree)] = dict(pm_force_n=pm.tolist(), copper_force_n=copper.tolist(),
                    action_reaction_error_n=balance, volume_m3=volume, joule_power_w=power,
                    current_moment_a_m=net.tolist())
                if not args.preflight_only:
                    loss_error = abs(power/source['joule_power_w']-1)
                    volume_error, geometry_error = volume_errors(volume,
                        original['geometric_volume_check']['mesh_volume_m3'], source['original_current_geometry']['volume_m3'])
                    current_error = float(np.linalg.norm(net))/max(np.sqrt(power/source['resistivity_ohm_m']*volume), 1e-300)
                    levels[str(degree)].update(power_relative_error=loss_error, volume_relative_error=volume_error,
                        mesh_cad_relative_difference=geometry_error, current_relative_error=current_error)
                    if balance > max(1e-8, .02*float(np.linalg.norm(pm))) or loss_error > 1e-8 or volume_error > 1e-9 or geometry_error > .02 or current_error > 1e-9:
                        report['failures'].append('Bare pose force/power/volume/current control at'+str(offset)+'degree'+str(degree))
            change = float(np.linalg.norm(np.asarray(levels['2']['pm_force_n'])-levels['4']['pm_force_n']))
            fine = np.asarray(levels['4']['pm_force_n'])
            limit = max(1e-8, .02*float(np.linalg.norm(fine)))
            report['poses'][str(offset)] = dict(magnets=model['magnets'], levels=levels, quadrature_change_n=change,
                quadrature_limit_n=limit, pm_force_n_per_loop_a=(fine/source['effective_loop_current_a']).tolist(),
                copper_force_n_per_loop_a=(np.asarray(levels['4']['copper_force_n'])/source['effective_loop_current_a']).tolist())
            if not args.preflight_only and change > limit:
                report['failures'].append('Bare pose quadrature refinement at'+str(offset))
            save()
        if not args.preflight_only:
            expected = np.asarray(reference['levels'][max(reference['levels'], key=int)]['pm_array_force_n'])
            actual = np.asarray(report['poses']['0.0']['levels']['4']['pm_force_n'])
            difference = float(np.linalg.norm(actual-expected));limit = max(1e-8, .05*float(np.linalg.norm(expected)))
            report['original_reference_control'] = dict(difference_n=difference, limit_n=limit, passed=difference <= limit)
            if difference > limit:
                report['failures'].append('Original independently sampled bare-force agreement')
        for path, digest in inputs.items():
            if sha(Path(path)) != digest:
                raise ValueError('Pose-force physical input changed during integration')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']:
                raise ValueError('Pose-force implementation changed during integration')
        seconds = time.monotonic()-started
        report.update(seconds=seconds, forecast_seconds=seconds*count/len(cells),
                      status='completed-bare-pose-runtime-preflight-only' if args.preflight_only else
                      ('failed' if report['failures'] else 'passed')+'-affine-rt0-bare-pose-forces-only')
        save()
        if report['failures']:
            raise ValueError('; '.join(report['failures']))
    except BaseException as error:
        report.update(status='failed-affine-rt0-bare-pose-forces', error=str(error), seconds=time.monotonic()-started)
        save();raise


if __name__ == '__main__':
    main()
