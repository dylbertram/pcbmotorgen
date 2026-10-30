"""Read-only fundamental phase-axis audit of an actual native move receipt.

The fitted reference describes the positive-sequence fundamental of the force
map. It does not invert a phase, infer controller wiring, or fit motor constants
to target performance. A non-120-degree winding stays visibly noncanonical.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def fundamental_audit(positions, forces, period_m, lower_m, upper_m):
    x = np.asarray(positions, dtype=float)
    f = np.asarray(forces, dtype=float)
    if x.ndim != 1 or f.shape != (len(x), 3) or not np.isfinite(x).all() or not np.isfinite(f).all():
        raise ValueError('Expected finite positions and three signed phase force coefficients')
    if not all(math.isfinite(v) for v in (period_m, lower_m, upper_m)) or period_m <= 0 or upper_m - lower_m < period_m:
        raise ValueError('Audit needs at least one electrical period of physical map data')
    selected = (x >= lower_m) & (x <= upper_m)
    if selected.sum() < 12:
        raise ValueError('Insufficient force positions for fundamental audit')
    theta = 2 * math.pi * x[selected] / period_m
    design = np.column_stack((np.ones(len(theta)), np.sin(theta), np.cos(theta)))
    coefficients, _, rank, _ = np.linalg.lstsq(design, f[selected], rcond=None)
    if rank != 3:
        raise ValueError('Degenerate harmonic sampling')
    dc, sine, cosine = coefficients
    beta = np.arange(3) * 2 * math.pi / 3
    # Average force for unit balanced sine amplitude over an electrical period.
    a = .5 * np.sum(sine * np.cos(beta) - cosine * np.sin(beta))
    b = .5 * np.sum(sine * np.sin(beta) + cosine * np.cos(beta))
    if math.hypot(a, b) <= 1e-10 * float(np.max(np.hypot(sine, cosine))):
        raise ValueError('No positive-sequence fundamental: check phase sequence/polarity rather than inventing electrical zero')
    reference = math.atan2(b, a) % (2 * math.pi)
    angles = np.arctan2(cosine, sine)
    # A canonical positive-sequence winding has angle_j + beta_j constant.
    residual = (angles + beta - reference + math.pi) % (2 * math.pi) - math.pi
    total = np.sum((f[selected] - f[selected].mean(axis=0)) ** 2, axis=0)
    if np.any(total <= 0):
        raise ValueError('No varying phase force to audit')
    return dict(interval_m=[lower_m, upper_m], positions_used=int(selected.sum()),
                phase_dc_n_per_a=dc.tolist(), phase_fundamental_amplitude_n_per_a=np.hypot(sine, cosine).tolist(),
                phase_sine_offset_deg=np.degrees(angles).tolist(),
                fundamental_fit_r_squared=(1 - np.sum((design @ coefficients - f[selected]) ** 2, axis=0) / total).tolist(),
                positive_sequence_reference_rad=reference,
                positive_sequence_reference_deg=math.degrees(reference),
                phase_axis_residual_from_120deg_deg=np.degrees(residual).tolist(),
                mean_positive_sequence_coupling_n_per_a=float(math.hypot(a, b)))


def audit(path):
    records = json.loads(path.read_text())
    native = records[-1] if isinstance(records, list) else records['native']
    result = native['result']
    demand = result['demand']
    electrical = demand['electrical']
    force_map = electrical['phase_model']['force_map']
    period = electrical['electrical_period_m']
    low, high = result['full_overlap_bounds_m']
    # Exclude one end period on either side; use a whole number of interior
    # periods, selected by geometry, not by the observed power or phase angle.
    low += period
    high = low + math.floor((high - period - low) / period) * period
    report = fundamental_audit([p['position_m'] for p in force_map],
                               [p['force_n_per_a'] for p in force_map], period, low, high)
    report.update(receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  input_sha256=native['input_sha256'],
                  phase_names=electrical['phase_model']['phase_names'],
                  configured_reference_rad=electrical['electrical_angle_at_zero_rad'],
                  source_kind='imported' if native['inputs'].get('cad_geometry') else 'generated',
                  trace_width_mm=(native['inputs']['cad_geometry']['trace_width_mm'] if native['inputs'].get('cad_geometry')
                                  else native['inputs']['config']['trace_width_m'] * 1000),
                  pcb_thickness_m=native['inputs']['config']['pcb_thickness_m'],
                  outer_copper_oz=native['inputs']['drive']['outer_copper_oz'],
                  inner_copper_oz=native['inputs']['drive']['inner_copper_oz'],
                  scope='Geometry fundamental audit, not controller calibration, rewiring, measured performance or a realizable optimal-current proof')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(audit(args.receipt), stream, indent=2, allow_nan=False)
        stream.write('\n')
