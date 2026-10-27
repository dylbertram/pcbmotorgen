import copy
import unittest

from audit_exterior_field_refinement import compare_fields


class ExteriorFieldRefinementTest(unittest.TestCase):
    def report(self):
        return dict(status='passed-two-exterior-source-points-only',failures=[],points_m=[[0.,0.,-1.]],trace_labels=['trace:A:1'],
            refinement_relative=[.001],agreement_relative=[.001],analytical_field_t=[[1.,0.,0.]],effective_loop_current_a=.5)

    def test_both_raw_basis_and_unfitted_per_amp_field_must_pass(self):
        a=self.report();b=copy.deepcopy(a);b['analytical_field_t']=[[1.001,0.,0.]]
        self.assertTrue(all(value['passed'] for value in compare_fields(a,b).values()))
        b['effective_loop_current_a']=.25
        self.assertFalse(compare_fields(a,b)['per_loop_a']['passed'])
        self.assertTrue(compare_fields(a,b)['saved_1v_basis']['passed'])

    def test_changed_points_or_failed_integration_rejected(self):
        for key,value in [('points_m',[[0.,0.,-2.]]),('refinement_relative',[.021]),('agreement_relative',[.051])]:
            b=self.report();b[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):compare_fields(self.report(),b)
