from copy import deepcopy
import unittest

from finite_current_coupling import CACHE_UNIT, control_model, current_pairs, validate_cache


class FiniteCurrentCouplingInputTest(unittest.TestCase):
    def cache(self):
        return dict(status='passed-finite-source-material-quadrature-only', failures=[], unit=CACHE_UNIT,
                    evaluated_points=100, total_material_points=100,
                    maximum_pointwise_opening_relative_change=.01,
                    maximum_direct_reference_relative_difference=.02,
                    storage={'maximum_relative_storage_error': 0.})

    def test_partial_failed_wrong_unit_or_nonfinite_cache_cannot_supply_results(self):
        validate_cache(self.cache())
        for key, value in [('status', 'running'), ('failures', ['unaccepted']), ('unit', 'tesla per1V'),
                           ('evaluated_points', 10), ('maximum_pointwise_opening_relative_change', .02001),
                           ('maximum_direct_reference_relative_difference', float('nan'))]:
            report = self.cache()
            report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_cache(report)

    def test_control_material_changes_are_explicit_and_do_not_mutate_original(self):
        model = {'stack': [{'name': 'ferrite', 'mu_r': 130., 'bsat_t': .25}, {'name': 'housing', 'mu_r': 1., 'bsat_t': None}]}
        original = deepcopy(model)
        self.assertEqual(control_model(model, 'nonlinear'), model)
        self.assertIsNone(control_model(model, 'linear')['stack'][0]['bsat_t'])
        self.assertEqual(control_model(model, 'vacuum')['stack'][0]['mu_r'], 1.)
        self.assertEqual(model, original)

    def test_declared_zero_and_polarity_states_are_not_synthesized(self):
        self.assertEqual(current_pairs([0., .1, -.1, .5, -.5]), [.1, .5])
        for values in [[.1, -.1], [0., 0.], [0., float('inf')]]:
            with self.assertRaises(ValueError):
                current_pairs(values)


if __name__ == '__main__':
    unittest.main()
