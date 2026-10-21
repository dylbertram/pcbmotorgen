from copy import deepcopy
import unittest

from compare_finite_current_controls import compare


class ForceControlTest(unittest.TestCase):
    def report(self):
        return dict(status='passed-recorded-finite-current-static-pilot-only', model={'case': 'actual'},
                    material_control='nonlinear', failures=[], formulation='vector-b',
                    states={'0.0': {'pm_array_force_n': [0., 0., 100.]}, '0.1': {'pm_array_force_n': [0., 0., 100.01]}})

    def test_large_bias_cannot_hide_failed_current_increment(self):
        first = self.report()
        second = deepcopy(first)
        second['states']['0.1']['pm_array_force_n'][2] = 100.02
        controls = compare(first, second, 'refinement')
        self.assertTrue(controls['0.1-total']['passed'])
        self.assertFalse(controls['0.1-increment']['passed'])

    def test_same_formulation_changed_pose_and_partial_reports_are_rejected(self):
        for key, value in [('formulation', 'vector-b'), ('status', 'running'), ('model', {'case': 'fixture'})]:
            first, second = self.report(), self.report()
            second['formulation'] = 'scalar-h'
            second[key] = value
            with self.assertRaises(ValueError):
                compare(first, second, 'formulation')

    def test_declared_floor_handles_zero_and_nonfinite_is_rejected(self):
        first = self.report()
        first['states'] = {'0.0': {'pm_array_force_n': [0., 0., 0.]}}
        second = deepcopy(first)
        second['states']['0.0']['pm_array_force_n'][0] = 1e-9
        self.assertTrue(compare(first, second, 'refinement')['0.0-total']['passed'])
        second['states']['0.0']['pm_array_force_n'][0] = float('nan')
        with self.assertRaises(ValueError):
            compare(first, second, 'refinement')
