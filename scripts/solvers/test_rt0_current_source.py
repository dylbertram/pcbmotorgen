import unittest

import numpy as np

from export_rt0_current_source import reconstruct_power


class Rt0CurrentSourceTest(unittest.TestCase):
    def setUp(self):
        self.cell = np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]])

    def test_constant_current_has_exact_volume_and_power(self):
        volume, power = reconstruct_power(self.cell, np.array([[2., 0., 0.]]), np.array([0.]), .3)
        self.assertAlmostEqual(volume[0], 1/6)
        self.assertAlmostEqual(power[0], .3*4/6)

    def test_radial_current_variance_is_preserved_not_smoothed_away(self):
        volume, power = reconstruct_power(self.cell, np.zeros((1, 3)), np.array([2.]), 1.)
        # Uniform unit-simplex covariance has trace9/80.
        self.assertAlmostEqual(power[0], volume[0]*4*9/80)
        self.assertGreater(power[0], 0.)

    def test_invalid_cell_or_current_arrays_fail_explicitly(self):
        with self.assertRaises(ValueError):
            reconstruct_power(self.cell, np.zeros((1, 3)), np.array([float('nan')]), 1.)
        with self.assertRaises(ValueError):
            reconstruct_power(self.cell*0, np.zeros((1, 3)), np.zeros(1), 1.)


if __name__ == '__main__':
    unittest.main()
