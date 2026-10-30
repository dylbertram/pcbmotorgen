"""Independent Magpylib functional cuboids for the prescribed alternating array.

No Rotation/Collection batching: recent SciPy identity-rotation batching can
produce size-dependent results. This scope has axis-aligned cuboids only.
"""
import magpylib
import numpy as np


def field_b(sim, observations):
    points = np.asarray(observations, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('Expected finite SI XYZ observations')
    field = np.zeros_like(points)
    for k in range(sim['magnet_count']):
        center = np.array([k * sim['magnet_pitch_m'], sim['board_width_m'] / 2,
                           sim['air_gap_m'] + sim['magnet_dims_m'][2] / 2])
        # Bound each public-API batch, including its internal identity rotation.
        # Large arrays in the current SciPy stack can corrupt even functional
        # API output. Chunking is tested against scalar and repeated-point data.
        for start in range(0, len(points), 256):
            end = min(start + 256, len(points))
            field[start:end] += magpylib.func.cuboid_field('B', observers=points[start:end] - center,
                dimensions=sim['magnet_dims_m'],
                polarizations=[0, 0, sim['magnet_remanence_t'] * (-1) ** k], squeeze=False)
    if not np.isfinite(field).all():
        raise ValueError('Nonfinite independent cuboid field')
    return field
