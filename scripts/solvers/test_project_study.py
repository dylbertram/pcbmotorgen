import unittest

from study_project_backplane import refinement_errors


class ProjectStudyTest(unittest.TestCase):
    def test_static_and_differential_refinements_are_separate(self):
        a={'static':{'field_ratio':1.1,'pressure_pa':200},'differential':{'coil_factors_per_phase':[1.004,1.06]}}
        self.assertTrue(refinement_errors(a,a)['passed'])
        b={'static':a['static'],'differential':{'coil_factors_per_phase':[1.,1.06]}}
        self.assertFalse(refinement_errors(a,b)['passed'])
        b={'static':{'field_ratio':1.1,'pressure_pa':210},'differential':a['differential']}
        self.assertFalse(refinement_errors(a,b)['passed'])


if __name__=='__main__':unittest.main()
