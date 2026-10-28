from copy import deepcopy
import unittest

from derive_copper_clearance_model import approved_model


class CopperClearanceModelTest(unittest.TestCase):
    def case(self):
        model = {'source_sha256': 'recorded-project', 'version_index': 1, 'magnets': [{'saved': True}], 'stack': [
            {'name': 'ferrite', 'origin_m': [-.018, -.006, -.0002], 'size_m': [.036, .012, .0002], 'mu_r': 130.},
            {'name': 'housing', 'origin_m': [-.018, -.006, -.0013], 'size_m': [.036, .012, .001], 'mu_r': 1.},
        ]}
        approval = dict(status='user-approved-derived-geometry', source_project_sha256='recorded-project', source_version_index=1,
                        move_policy='translate-entire-backplane-stack-downward', copper_to_ferrite_clearance_m=35e-6,
                        **{k: True for k in ['preserve_copper', 'preserve_magnets', 'preserve_layer_thicknesses',
                                            'preserve_internal_stack_gaps', 'preserve_root_files']})
        return model, [{'low_z_m': -17.5e-6}], approval

    def test_approved_clearance_preserves_copper_magnets_thickness_and_internal_gap(self):
        model, intervals, approval = self.case()
        original = deepcopy(model)
        result, delta = approved_model(model, intervals, approval)
        self.assertEqual(model, original)
        self.assertAlmostEqual(delta, -52.5e-6)
        self.assertEqual(result['magnets'], original['magnets'])
        self.assertEqual(result['stack'][0]['size_m'], original['stack'][0]['size_m'])
        self.assertAlmostEqual(result['stack'][0]['origin_m'][2]+.0002, -52.5e-6)
        self.assertAlmostEqual(result['stack'][1]['origin_m'][2]+.001, -352.5e-6)

    def test_missing_or_wrong_approval_cannot_silently_fix_a_model(self):
        for key, value in [('status', 'unapproved'), ('source_project_sha256', 'other'),
                           ('source_version_index', 2), ('move_policy', 'cut-ferrite'),
                           ('preserve_copper', False), ('copper_to_ferrite_clearance_m', -1.),
                           ('copper_to_ferrite_clearance_m', float('nan'))]:
            model, intervals, approval = self.case()
            approval[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                approved_model(model, intervals, approval)

    def test_explicit_contact_is_distinct_from_an_invented_insulating_gap(self):
        model, intervals, approval = self.case()
        approval['copper_to_ferrite_clearance_m'] = 0.
        _, delta = approved_model(model, intervals, approval)
        self.assertAlmostEqual(delta, -17.5e-6)

    def test_downward_approval_does_not_authorize_upward_changes(self):
        model, intervals, approval = self.case()
        for region in model['stack']:
            region['origin_m'][2] -= .001
        with self.assertRaises(ValueError):
            approved_model(model, intervals, approval)


if __name__ == '__main__':
    unittest.main()
