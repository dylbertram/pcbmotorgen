"""Decompose generated winding force by copper layer using independent R/I/B.

Read-only diagnostic. Connectivity comes from the exported graph; currents and
the prescribed free-space PM field are independently reconstructed. No terminal
reversal, geometry correction or controller qualification is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from prescribed_pm_oracle import field_b
from winding_oracle import conductor_samples, resistances, unit_currents


def harmonic(x, force, period):
    theta = 2 * np.pi * x / period
    basis = np.column_stack((np.ones(len(x)), np.sin(theta), np.cos(theta)))
    coefficients, _, rank, _ = np.linalg.lstsq(basis, force, rcond=None)
    if rank != 3:
        raise ValueError('Degenerate layer-force sampling')
    return dict(dc_n_per_a=float(coefficients[0]),
                amplitude_n_per_a=float(np.hypot(*coefficients[1:])),
                sine_offset_deg=float(np.degrees(np.arctan2(coefficients[2], coefficients[1]))))


def audit(fixture_path, force_path):
    fixture = json.loads(fixture_path.read_text())
    native = json.loads(force_path.read_text())
    native = native.get('signed_force_audit') or native
    if fixture['force_subdivisions'] != native['meshing']:
        raise ValueError('Conductor meshes differ')
    sim, settings, hints = fixture['sim'], fixture['drive'], fixture['geometry_hints']
    if sim.get('backplane') is not None:
        raise ValueError('Free-space oracle cannot validate a material stack')
    # Fixed geometry-selected interior samples, not chosen by force or power.
    selected = native['force_map'][40:113:3]
    x = np.array([point['position_m'] for point in selected])
    reference = np.array([point['force_n_per_a'] for point in selected])
    report = dict(scope=__doc__, fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                  native_map_sha256=hashlib.sha256(force_path.read_bytes()).hexdigest(), phases={})
    for phase_index, network in enumerate(fixture['networks']):
        if network['net'] != native['phase_names'][phase_index]:
            raise ValueError('Phase order mismatch')
        shares, resistance = unit_currents(network, resistances(network, sim, settings, hints))
        points, dl = conductor_samples(network, shares, sim, hints, native['meshing'])
        groups = np.concatenate([np.full(
            (len(edge['geometry'].get('points_m', [0, 1])) - 1) * native['meshing'],
            edge['geometry'].get('layer', sim['num_layers']), dtype=int)
            for edge in network['edges']])
        if len(groups) != len(points):
            raise ValueError('Sample grouping differs from independent geometry')
        forces = []
        for position in x:
            observations = points.copy()
            observations[:, 0] -= position
            field = field_b(sim, observations)
            axial = -np.cross(dl, field)[:, 0]
            forces.append([float(axial[groups == layer].sum()) for layer in range(sim['num_layers'] + 1)])
        forces = np.asarray(forces)
        total = forces.sum(axis=1)
        np.testing.assert_allclose(total, reference[:, phase_index], rtol=1e-8, atol=1e-10)
        layers = {str(layer) if layer < sim['num_layers'] else 'vias': harmonic(x, forces[:, layer], native['electrical_period_m'])
                  for layer in range(sim['num_layers'] + 1)}
        combined = harmonic(x, total, native['electrical_period_m'])
        amplitude_sum = sum(layer['amplitude_n_per_a'] for layer in layers.values())
        report['phases'][network['net']] = dict(resistance_hot_ohm=resistance,
            layers=layers, combined=combined,
            retained_amplitude_fraction=combined['amplitude_n_per_a'] / amplitude_sum,
            max_independent_force_error_n_per_a=float(np.max(abs(total - reference[:, phase_index]))),
            positions_m=x.tolist(), layer_force_n_per_a=forces.tolist())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('native_map', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.fixture, args.native_map)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
