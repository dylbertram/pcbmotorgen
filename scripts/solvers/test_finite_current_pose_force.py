import unittest

import numpy as np

from finite_current_pose_force import batches, volume_errors


class AffinePoseSourceTest(unittest.TestCase):
    def test_strict_reload_volume_uses_saved_mesh_not_distinct_cad_volume(self):
        reload_error, geometry_error = volume_errors(2.73979586336266e-8, 2.7397958633626786e-8, 2.7484132285453057e-8)
        self.assertLess(reload_error, 1e-9)
        self.assertLess(geometry_error, .02)
        self.assertGreater(geometry_error, .003)
        wrong, _ = volume_errors(2.74e-8, 2.7397958633626786e-8, 2.7484132285453057e-8)
        self.assertGreater(wrong, 1e-9)
    def test_real_volume_weights_and_radial_term_survive_batching(self):
        cells = np.array([[[0., 0., 0.], [2., 0., 0.], [0., 3., 0.], [0., 0., 4.]]])
        mean = np.array([[1., 2., -3.]])
        slope = np.array([.7])
        local = np.array([[.25, .25, .25], [.1, .2, .3]])
        weights = np.array([1/12, 1/12])
        points, current, physical = next(batches(cells, mean, slope, local, weights, 1))
        np.testing.assert_allclose(physical.sum(), 4.)
        np.testing.assert_allclose(current, mean+.7*(points-cells.mean(axis=1)))
        self.assertGreater(np.linalg.norm(current[1]-mean[0]), 0.)

    def test_degenerate_cells_are_not_replaced_or_softened(self):
        with self.assertRaises(ValueError):
            next(batches(np.zeros((1, 4, 3)), np.zeros((1, 3)), np.zeros(1), np.zeros((1, 3)), np.ones(1)))
