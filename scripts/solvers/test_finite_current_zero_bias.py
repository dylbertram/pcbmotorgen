import unittest

from finite_current_zero_bias import magnetic_regions, posed_model


class ZeroBiasMaterialTagTest(unittest.TestCase):
    def test_recorded_pose_changes_only_pm_x_without_mutating_design(self):
        model = {'magnets': [{'origin_m': [0., 0., .001]}], 'stack': [{'mu_r': 130.}]}
        result = posed_model(model, 1e-4)
        self.assertEqual(result['magnets'][0]['origin_m'], [1e-4, 0., .001])
        self.assertEqual(model['magnets'][0]['origin_m'], [0., 0., .001])
        self.assertEqual(model['stack'], result['stack'])
        for value in [1.0001e-4, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                posed_model(model, value)

    def test_vacuum_control_keeps_former_ferrite_in_vacuum_energy_domain(self):
        model = {'stack': [{'name': 'ferrite', 'mu_r': 1.}, {'name': 'housing', 'mu_r': 1.}]}
        self.assertEqual(magnetic_regions(model, ['air', 'ferrite', 'housing']), [])
        model['stack'][0]['mu_r'] = 130.
        self.assertEqual([x['name'] for x in magnetic_regions(model, ['air', 'ferrite', 'housing'])], ['ferrite'])

    def test_missing_or_duplicate_interfaces_and_unsupported_housing_fail(self):
        model = {'stack': [{'name': 'ferrite', 'mu_r': 130.}, {'name': 'housing', 'mu_r': 1.}]}
        with self.assertRaises(ValueError):
            magnetic_regions(model, ['air', 'housing'])
        model['stack'][1]['mu_r'] = 1.02
        with self.assertRaises(ValueError):
            magnetic_regions(model, ['air', 'ferrite', 'housing'])


if __name__ == '__main__':
    unittest.main()
