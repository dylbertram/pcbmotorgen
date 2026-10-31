import unittest

import magpylib
import numpy as np

from prescribed_pm_oracle import field_b


class PrescribedPmOracleTest(unittest.TestCase):
    def test_scalar_object_api_agrees_and_batch_size_does_not_change_field(self):
        sim = dict(magnet_count=5, magnet_pitch_m=.006, board_width_m=.008,
                   air_gap_m=.0005, magnet_dims_m=[.005, .005, .003], magnet_remanence_t=1.34)
        points = np.column_stack((np.linspace(-.01, .04, 257), np.full(257, .004), np.full(257, -.0008)))
        whole = field_b(sim, points)
        chunks = np.concatenate([field_b(sim, points[i:i + 7]) for i in range(0, len(points), 7)])
        np.testing.assert_allclose(whole, chunks, rtol=1e-12, atol=1e-14)
        # Reproduce the large native conductor-array regime, not only tiny
        # samples that miss the upstream rotation-batching failure.
        repeated = field_b(sim, np.tile(points, (130, 1)))
        np.testing.assert_allclose(repeated, np.tile(whole, (130, 1)), rtol=1e-12, atol=1e-14)
        for i in [0, 128, 256]:
            independent = np.zeros(3)
            for k in range(sim['magnet_count']):
                magnet = magpylib.magnet.Cuboid(dimension=sim['magnet_dims_m'],
                    polarization=[0, 0, sim['magnet_remanence_t'] * (-1) ** k],
                    position=[k * sim['magnet_pitch_m'], .004, .002])
                independent += magnet.getB(points[i])
            np.testing.assert_allclose(whole[i], independent, rtol=1e-12, atol=1e-14)


if __name__ == '__main__':
    unittest.main()
