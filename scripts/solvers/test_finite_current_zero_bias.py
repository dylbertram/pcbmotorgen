import unittest

from finite_current_zero_bias import magnetic_regions, posed_model, accepted_material_mesh


class ZeroBiasMaterialTagTest(unittest.TestCase):
    def test_accepted_bias_can_supply_its_exact_material_mesh_to_a_new_pose(self):
        model = {'case': 'approved'}
        report = dict(status='passed-recorded-zero-current-bias-controls-only', failures=[],
                      model=model, version='pinned')
        accepted_material_mesh(report, model, 'pinned')
        for key, value in [('status', 'running'), ('failures', ['failed']), ('version', 'different'), ('model', {'case': 'other'})]:
            changed = dict(report, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                accepted_material_mesh(changed, model, 'pinned')

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
