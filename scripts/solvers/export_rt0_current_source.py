#!/usr/bin/env python3
"""Export an immutable accepted affine RT0 current source without refitting it.

Keeps every tetrahedron, mean current and radial RT0 coefficient. No centreline,
softened radius, node smoothing, branch lookup or constant-current approximation.
Checks reconstructed volume, Joule power, divergence and mean-current identities.
This is source preparation, not nonlinear magnetic or hardware qualification.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_finite_dc_controls import MIXED, load
from post_project_force import sha
from source_snapshot import capture


def reconstruct_power(cells, mean_current, slope, resistivity):
    cells = np.asarray(cells, dtype=float)
    mean_current, slope = np.asarray(mean_current, dtype=float), np.asarray(slope, dtype=float)
    if cells.ndim != 3 or cells.shape[1:] != (4, 3) or mean_current.shape != (len(cells), 3) or slope.shape != (len(cells),):
        raise ValueError('Invalid affine RT0 arrays')
    if not all(np.isfinite(x).all() for x in [cells, mean_current, slope]) or not np.isfinite(resistivity) or resistivity <= 0:
        raise ValueError('Finite RT0 geometry/current and physical resistivity required')
    volume = abs(np.linalg.det(cells[:, 1:]-cells[:, :1]))/6
    if np.any(volume <= 0):
        raise ValueError('Degenerate source cell')
    centred = cells-cells.mean(axis=1)[:, None, :]
    # A tetrahedron's uniform covariance is sum(vertex deviations outer products)/20.
    second_moment = np.sum(centred*centred, axis=(1, 2))/20
    power = resistivity*volume*(np.sum(mean_current*mean_current, axis=1)+slope*slope*second_moment)
    return volume, power


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-work', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    origin, work = args.current_work.resolve(), args.work.resolve()
    if work.exists():
        parser.error('Preserve previous source exports')
    source = load(origin, MIXED)
    if source['request']['geometry_order'] != 1:
        raise ValueError('Affine RT0 export refuses curved current cells')
    geometry_path = next(Path(p).with_name('summary.json') for p in source['input_hashes'] if p.endswith('/copper.brep'))
    geometry = json.loads(geometry_path.read_text())
    rho = geometry['geometry']['copper_resistivity_ohm_m']
    inputs = {str(origin/name): sha(origin/name) for name in ['summary.json', 'mesh.vol', 'dc-current-potential.sol']}
    inputs[str(geometry_path)] = sha(geometry_path)
    import ngsolve as ng
    if ng.__version__ != source['version']:
        raise ValueError('Current source engine changed')
    started = time.monotonic()
    mesh = ng.Mesh(str(origin/'mesh.vol'))
    space = ng.HDiv(mesh, order=0)*ng.L2(mesh, order=0)
    solution = ng.GridFunction(space)
    solution.Load(str(origin/'dc-current-potential.sol'))
    current = solution.components[0]
    vertices = np.array([tuple(v.point) for v in mesh.vertices])
    indices = np.empty((mesh.ne, 4), dtype=np.int64)
    for i, element in enumerate(mesh.Elements()):
        if element.nr != i or element.type != ng.ET.TET:
            raise ValueError('Unsupported element ordering/type')
        indices[i] = [v.nr for v in element.vertices]
    cells = vertices[indices]
    volume = abs(np.linalg.det(cells[:, 1:]-cells[:, :1]))/6
    if np.any(volume <= 0):
        raise ValueError('Degenerate affine source geometry')
    mean = np.column_stack([np.asarray(ng.Integrate(current[i], mesh, order=2, element_wise=True))/volume for i in range(3)])
    slope = np.asarray(ng.Integrate(ng.div(current), mesh, order=2, element_wise=True))/(3*volume)
    checked_volume, power = reconstruct_power(cells, mean, slope, rho)
    total = float(power.sum())
    volume_error = abs(float(checked_volume.sum())/source['geometric_volume_check']['mesh_volume_m3']-1)
    power_error = abs(total/source['dc']['joule_power_w']-1)
    moment = np.sum(mean*volume[:, None], axis=0)
    moment_relative = float(np.linalg.norm(moment))/max(np.sqrt(total/rho*volume.sum()), 1e-300)
    if volume_error > 1e-9 or power_error > 1e-8 or moment_relative > 1e-9:
        raise ValueError('Original source volume/power/current reload controls failed')
    # Pointwise identity checks are deterministic held-out cells, not an affine
    # fit. The original basis/geometry guarantee the same polynomial everywhere.
    selected = np.unique(np.linspace(0, mesh.ne-1, min(64, mesh.ne), dtype=int))
    rule = ng.IntegrationRule(points=[(.1, .2, .3), (.3, .1, .2)], weights=[1., 1.])
    coordinate = ng.CoefficientFunction((ng.x, ng.y, ng.z))
    maximum = 0.
    for i in selected:
        element = mesh[ng.ElementId(ng.VOL, int(i))]
        mapped = mesh.GetTrafo(element)(rule)
        points = np.asarray(coordinate(mapped)).reshape(-1, 3)
        actual = np.asarray(current(mapped)).reshape(-1, 3)
        reconstructed = mean[i]+slope[i]*(points-cells[i].mean(axis=0))
        error = float(np.max(np.linalg.norm(actual-reconstructed, axis=1)))
        scale = max(float(np.max(np.linalg.norm(actual, axis=1))), 1.)
        maximum = max(maximum, error/scale)
    if maximum > 1e-8:
        raise ValueError('Current basis is not represented by the exported RT0 coefficients')
    work.mkdir(parents=True)
    archive = work/'rt0-source.npz'
    np.savez_compressed(archive, vertices_m=vertices, cells=indices, mean_current_a_m2=mean, radial_slope_a_m3=slope)
    report = {'status': 'passed-affine-rt0-source-export-only', 'scope': __doc__, 'version': ng.__version__,
              'source_work': str(origin), 'input_hashes': inputs, 'archive_sha256': sha(archive),
              'resistivity_ohm_m': rho, 'effective_loop_current_a': source['dc']['effective_loop_current_a'],
              'elements': mesh.ne, 'vertices': len(vertices), 'joule_power_w': total,
              'volume_relative_error': volume_error, 'power_relative_error': power_error,
              'net_current_relative_error': moment_relative, 'maximum_held_out_affine_identity_relative_error': maximum,
              'held_out_cells': len(selected), 'mean_current_moment_a_m': moment.tolist(),
              'integrated_divergence_squared': float(np.sum((3*slope)**2*volume)),
              'original_current_geometry': source['geometry'],
              'source_snapshots': capture(work, [Path(__file__), Path(__file__).with_name('audit_finite_dc_controls.py')]),
              'seconds': time.monotonic()-started}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Current source changed during export')
    (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(report['status'], mesh.ne, 'cells', 'power error', power_error, 'identity error', maximum, flush=True)


if __name__ == '__main__':
    main()
