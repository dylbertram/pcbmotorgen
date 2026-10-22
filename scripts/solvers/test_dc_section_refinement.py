import copy
import unittest

from audit_dc_section_refinement import compare_sections


class LocalCurrentRefinementTest(unittest.TestCase):
    def report(self,current=.5):
        return dict(status='passed-finite-dc-all-eligible-winding-sections-only',failures=[],selection='all eligible',expected_sections=1,
            sections=[dict(label='via:A:1',centre_m=[0.,0.,0.],normal=[0.,0.,1.],window_half_width_m=.001,
                reference_per_loop_a=.5,current_per_loop_a=current,area_m2=1.,passed=True)])

    def test_original_two_percent_and_near_zero_floor(self):
        self.assertTrue(compare_sections(self.report(),self.report(.501))[0]['passed'])
        self.assertFalse(compare_sections(self.report(),self.report(.52))[0]['passed'])
        self.assertTrue(compare_sections(self.report(0.),self.report(1e-9))[0]['passed'])
        self.assertFalse(compare_sections(self.report(0.),self.report(2e-8))[0]['passed'])

    def test_changed_or_incomplete_physical_inventory_rejected(self):
        for key,value in [('centre_m',[1.,0.,0.]),('reference_per_loop_a',-.5),('label','via:A:2')]:
            report=self.report();report['sections'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):compare_sections(self.report(),report)
        for key,value in [('expected_sections',2),('selection','sampled'),('failures',['via:A:1'])]:
            report=self.report();report[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):compare_sections(self.report(),report)
