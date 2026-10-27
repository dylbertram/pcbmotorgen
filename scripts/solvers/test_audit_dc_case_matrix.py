from copy import deepcopy
import unittest

from audit_dc_case_matrix import ACCEPTED, CURRENTS, matrix_plan, validate_state_report, comparison_order


class CaseMatrixAuditTest(unittest.TestCase):
    def test_refinement_uses_finer_mesh_domain_opening_or_degree8_denominator(self):
        self.assertEqual(comparison_order('case/refined', 'case/coarse', 'refinement'), ('case/coarse', 'case/refined'))
        self.assertEqual(comparison_order('case/quadrature', 'case/coarse', 'refinement'), ('case/quadrature', 'case/coarse'))
        self.assertEqual(comparison_order('vector', 'scalar', 'formulation'), ('vector', 'scalar'))

    def test_matrix_contains_every_pose_formulation_and_control(self):
        jobs, pairs = matrix_plan()
        self.assertEqual(len(jobs), 37)
        self.assertEqual(len(pairs), 44)
        for pose in ['nominal', 'plus100um', 'minus100um']:
            for formulation in ['vector', 'scalar']:
                for control in ['coarse', 'refined', 'domain', 'quadrature']:
                    self.assertIn(pose+'/'+formulation+'/'+control, jobs)

    def test_missing_currents_nonfinite_force_and_failed_residual_are_rejected(self):
        model = {'magnets': [], 'stack': []}
        state = dict(pm_array_force_n=[0., 0., 1.], combined_stationary_force_n=[0., 0., -1.], relative_residual=1e-12)
        report = dict(status=ACCEPTED, failures=[], model=model, formulation='vector-b', field_order=1, degree=8,
                      states={key: deepcopy(state) for key in CURRENTS},
                      incremental_balance={key: {'passed': True} for key in CURRENTS-{'0.0'}})
        validate_state_report(report, model, 'nonlinear', 0., 'vector-b', 1, 8)
        for mutation in ['missing', 'nan', 'residual', 'partial']:
            bad = deepcopy(report)
            if mutation == 'missing':del bad['states']['-0.5']
            if mutation == 'nan':bad['states']['0.1']['pm_array_force_n'][0] = float('nan')
            if mutation == 'residual':bad['states']['0.1']['relative_residual'] = 1e-6
            if mutation == 'partial':bad['status'] = 'running'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_state_report(bad, model, 'nonlinear', 0., 'vector-b', 1, 8)
