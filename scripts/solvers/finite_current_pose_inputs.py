"""Reject mismatched or partial finite-current bare-pose references."""
from pathlib import Path

import numpy as np

from finite_current_zero_bias import posed_model


def pose_forces(cache, bias, reference, offset, source_hash, loop_current):
    model = posed_model(cache['model'], offset)
    if model != bias['model']:
        raise ValueError('PM pose differs from the explicitly solved zero-current baseline')
    if reference.get('status') != 'passed-affine-rt0-bare-pose-forces-only' or reference.get('failures'):
        raise ValueError('Whole accepted finite-cell bare-pose force reference required')
    if reference.get('original_reference_control', {}).get('passed') is not True:
        raise ValueError('Original independent bare-force agreement is missing')
    if (reference['model'] != cache['model'] or reference['source_work'] != cache['source_work'] or
        reference['input_hashes'].get(str(Path(cache['source_work'])/'summary.json')) != source_hash or
        reference['effective_loop_current_a'] != loop_current or not np.isfinite(loop_current) or loop_current <= 0):
        raise ValueError('Bare-pose reference belongs to a different immutable finite-current source')
    pose = reference['poses'].get(str(float(offset)))
    if pose is None or pose['magnets'] != model['magnets']:
        raise ValueError('Missing exact physical PM-pose force reference')
    for degree in ['2', '4']:
        level = pose['levels'][degree]
        field = np.asarray(level['pm_force_n'])
        opposite = np.asarray(level['copper_force_n'])
        balance = level['action_reaction_error_n']
        controls = [level['power_relative_error'], level['volume_relative_error'], level['current_relative_error'],
                    level.get('mesh_cad_relative_difference', float('nan')), balance]
        if (field.shape != (3,) or opposite.shape != (3,) or not np.isfinite([field, opposite]).all() or not np.isfinite(controls).all() or
            min(controls) < 0 or any(x > limit for x, limit in zip(controls,
                [1e-8, 1e-9, 1e-9, .02, max(1e-8, .02*float(np.linalg.norm(field)))]))):
            raise ValueError('Bare-pose source/power/force control failed')
        if np.linalg.norm(field+opposite) > max(1e-8, .02*float(np.linalg.norm(field))):
            raise ValueError('Bare-pose action/reaction vectors disagree')
    first, last = [np.asarray(pose['levels'][degree]['pm_force_n']) for degree in ['2', '4']]
    if np.linalg.norm(first-last) > max(1e-8, .02*float(np.linalg.norm(last))):
        raise ValueError('Bare-pose force quadrature refinement failed')
    pm, copper = [np.asarray(pose[key], dtype=float) for key in ['pm_force_n_per_loop_a', 'copper_force_n_per_loop_a']]
    if any(vector.shape != (3,) or not np.isfinite(vector).all() for vector in [pm, copper]):
        raise ValueError('Finite three-component bare forces per loop ampere required')
    for actual, expected in [(pm, last/loop_current), (copper, np.asarray(pose['levels']['4']['copper_force_n'])/loop_current)]:
        if np.linalg.norm(actual-expected) > max(1e-15, 1e-12*float(np.linalg.norm(expected))):
            raise ValueError('Bare-pose force units differ from the saved effective loop current')
    return model, pm, copper
