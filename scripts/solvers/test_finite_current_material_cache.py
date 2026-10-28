import unittest

import numpy as np

from cache_finite_current_material_source import relative_difference


class MaterialSourceComparisonTest(unittest.TestCase):
    def test_vector_error_uses_declared_near_zero_floor(self):
        first = np.array([[3.03, 4.04, 0.], [0., 0., 1e-14]])
        second = np.array([[3., 4., 0.], [0., 0., 0.]])
        np.testing.assert_allclose(relative_difference(first, second, 1e-12), [.01, .01])

    def test_invalid_or_nonfinite_comparisons_cannot_pass_via_nan(self):
        good = np.zeros((1, 3))
        for first, second, floor in [(good, good, 0.), (good, good, float('nan')),
                                     (good, np.zeros((2, 3)), 1e-12),
                                     (np.array([[float('nan'), 0., 0.]]), good, 1e-12)]:
            with self.assertRaises(ValueError):
                relative_difference(first, second, floor)


if __name__ == '__main__':
    unittest.main()
