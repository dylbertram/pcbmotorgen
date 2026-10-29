import math
import unittest

import numpy as np

from audit_move_commutation import fundamental_audit


class CommutationAuditTest(unittest.TestCase):
    def test_known_balanced_winding_recovers_electrical_zero(self):
        x = np.linspace(0, .048, 193)
        phi = .71
        f = np.array([[.2 * math.sin(2 * math.pi * p / .012 + phi - j * 2 * math.pi / 3) for j in range(3)] for p in x])
        result = fundamental_audit(x, f, .012, .012, .036)
        self.assertAlmostEqual(result['positive_sequence_reference_rad'], phi, places=12)
        self.assertTrue(all(abs(v) < 1e-10 for v in result['phase_axis_residual_from_120deg_deg']))
        self.assertAlmostEqual(result['mean_positive_sequence_coupling_n_per_a'], .3, places=12)

    def test_sixty_degree_axes_are_not_silently_rewired_into_balanced_winding(self):
        x = np.linspace(0, .048, 193)
        f = np.array([[math.sin(2 * math.pi * p / .012 + math.radians(70 - j * 60)) for j in range(3)] for p in x])
        original = f.copy()
        result = fundamental_audit(x, f, .012, .012, .036)
        np.testing.assert_array_equal(f, original)
        np.testing.assert_allclose(result['phase_sine_offset_deg'], [70, 10, -50], atol=1e-10)
        self.assertAlmostEqual(result['positive_sequence_reference_deg'], 130, places=10)
        np.testing.assert_allclose(result['phase_axis_residual_from_120deg_deg'], [-60, 0, 60], atol=1e-10)
        # A mathematical polarity reversal is distinguishable from changing
        # electrical zero. Never apply this to the actual saved winding.
        hypothetical = f * np.array([1, -1, 1])
        # Reversing B yields 120-degree axes but the opposite sequence.
        with self.assertRaisesRegex(ValueError, 'phase sequence/polarity'):
            fundamental_audit(x, hypothetical, .012, .012, .036)
        reversed_b = fundamental_audit(x, hypothetical[:, [0, 2, 1]], .012, .012, .036)
        self.assertAlmostEqual(reversed_b['positive_sequence_reference_deg'], 70, places=10)
        np.testing.assert_allclose(reversed_b['phase_axis_residual_from_120deg_deg'], [0, 0, 0], atol=1e-10)

    def test_rejects_short_or_nonfinite_maps(self):
        with self.assertRaises(ValueError):
            fundamental_audit([0, .001], [[1, 2, 3]] * 2, .012, 0, .001)
        with self.assertRaises(ValueError):
            fundamental_audit([float('nan')], [[1, 2, 3]], .012, 0, .024)


if __name__ == '__main__':
    unittest.main()
