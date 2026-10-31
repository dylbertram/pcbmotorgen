import unittest

import numpy as np

from check_housing_motion_reference import fem_mode,reference,case_base


class HousingMotionReferenceTest(unittest.TestCase):
    def test_performance_goals_do_not_change_reference_loss(self):
        case=case_base();case['speed_m_s']=2.
        baseline=reference(case,24,samples=32)
        case['sim'].update(target_force_n=100.,peak_force_n=.001,max_accel_m_s2=0.,max_temperature_rise_c=0.)
        self.assertEqual(reference(case,24,samples=32),baseline)

    def test_insulating_limit_has_no_joule_power(self):
        loss,work=fem_mode(500.,1000.,[(1.,0.,.001)],24)
        np.testing.assert_array_equal(loss,[0.]);self.assertAlmostEqual(work,0.)

    def test_weak_conductivity_limit_matches_analytical_exponential(self):
        k=500.;omega=1000.;sigma=.1;thickness=.001
        loss,_=fem_mode(k,omega,[(1.,sigma,thickness)],192)
        expected=sigma*(omega/k)**2*(1-np.exp(-2*k*thickness))/(2*k)
        self.assertLess(abs(loss[0]/expected-1),1e-4)

    def test_reverse_and_zero_have_nonnegative_loss(self):
        a=case_base();a['speed_m_s']=0.
        self.assertEqual(reference(a,24)['regions_w'],[0.,0.])
        a['speed_m_s']=2.;x=reference(a,48,samples=64)
        a['speed_m_s']=-2.;y=reference(a,48,samples=64)
        self.assertEqual(x,y);self.assertGreater(x['regions_w'][-1],0.);self.assertLess(x['balance'],1e-8)
