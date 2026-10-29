import math
import unittest

import numpy as np

from practical_move_assumptions import screening_assumptions, slab_skin_increment


def inputs():
    return dict(voltage=12, pwm_hz=100_000, phase_inductance_h=47e-6,
                winding_temp_c=75, phase_names=["A", "B", "C"],
                driver_path_ohm=.21, external_inductance_h=47e-6,
                phase_resistance_ohm=2.5,
                phase_resistances_ohm=[2.4, 2.5, 2.6], copper_thickness_m=35e-6,
                electrical_period_m=.012,
                max_phase_peak_a=5, max_speed_m_s=1)


def ripple():
    return 12 / 5 * math.tanh(2.5 / (4 * 100_000 * 47e-6))


class PracticalAssumptionsTest(unittest.TestCase):
    def test_balanced_covariance_matches_explicit_pair_triangle_samples(self):
        model = screening_assumptions(**inputs())
        delta = ripple()
        t = (np.arange(60000) + .5) / 60000
        triangle = delta * (0.5 - np.abs(2 * t - 1))
        samples = np.concatenate([triangle[:, None] * pair for pair in
            [np.array([1., -1., 0.]), np.array([0., 1., -1.]), np.array([-1., 0., 1.])]])
        np.testing.assert_allclose(samples.mean(axis=0), 0, atol=1e-14)
        np.testing.assert_allclose(samples.T @ samples / len(samples), model['ripple']['covariance_a2'], rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(samples.sum(axis=1), 0, atol=1e-14)

    def test_driver_cycle_laws_match_electrical_cycle_rms_formulas(self):
        model = screening_assumptions(**inputs())
        theta = 2 * np.pi * (np.arange(100000) + .5) / 100000
        current = np.sin(theta[:, None] - np.arange(3) * 2 * np.pi / 3)
        sum_abs = np.abs(current).sum(axis=1).mean()
        switching = 100_000 * model['switching']['abs_mean_current_j_per_a'] * sum_abs
        dead = 100_000 * model['deadtime']['abs_mean_current_j_per_a'] * sum_abs
        self.assertAlmostEqual(switching, 3 / math.sqrt(2) * 12 * 96e-9 * 100_000, places=10)
        self.assertAlmostEqual(dead, 6 / math.sqrt(2) * .7 * 200e-9 * 100_000, places=10)

    def test_inductor_q_loss_and_missing_terms_are_not_double_counted(self):
        model = screening_assumptions(**inputs())
        self.assertAlmostEqual(model['external_series_resistance_ohm'][0], .0741 * (1 + .00393 * 50))
        delta = ripple()
        expected = (2 * math.pi * 100_000 * 47e-6 / 20 - .0741) * (2 / 3) * (math.sqrt(8) / math.pi**2 * delta)**2
        self.assertAlmostEqual(model['external_core_loss_w'][0], expected)
        self.assertTrue(model['omitted_losses'])
        no_inductor = screening_assumptions(**{**inputs(), 'external_inductance_h': 0.0})
        self.assertEqual(no_inductor['external_core_loss_w'], [0., 0., 0.])
        with self.assertRaises(ValueError):
            screening_assumptions(**{**inputs(), 'voltage': 24})

    def test_rl_ripple_matches_independent_marched_half_cycles(self):
        r, l, v, f = 2.5, 1e-6, 12., 100_000.
        a = math.exp(-r / (2 * f * l))
        current = 0.0
        for _ in range(100):
            hi = v / (4 * r) + (current - v / (4 * r)) * a
            current = -v / (4 * r) + (hi + v / (4 * r)) * a
        expected = hi - current
        model = screening_assumptions(**{**inputs(), 'phase_inductance_h': l, 'phase_resistance_ohm': r})
        self.assertAlmostEqual(2 * model['ripple']['peak_deviation_a'][0], expected, places=12)

    def test_slab_skin_matches_independent_complex_impedance(self):
        import cmath
        rho, f, t = 2.1e-8, 100_000., 35e-6
        delta = math.sqrt(rho / (math.pi * f * 4 * math.pi * 1e-7))
        z = (1 + 1j) * t / (2 * delta)
        independent = (z / cmath.tanh(z)).real - 1
        self.assertAlmostEqual(slab_skin_increment(rho, f, t), independent, places=12)
        model = screening_assumptions(**inputs())
        self.assertGreater(model['winding_ripple_ac_increment_ohm'][0], 0)
        self.assertGreater(model['winding_ripple_ac_increment_ohm'][0], model['winding_fundamental_ac_increment_ohm'][0])


if __name__ == '__main__':
    unittest.main()
