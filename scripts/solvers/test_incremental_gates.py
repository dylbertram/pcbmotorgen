import unittest

import numpy as np

from check_spectral_incremental import factor_errors, knee_points
from spectral_plate import MU0


class IncrementalGateTest(unittest.TestCase):
    def test_knee_table_refinement_preserves_the_exact_constitutive_law(self):
        for mu,bsat in [(130,0.25),(2500,0.45)]:
            coarse=knee_points(mu,bsat,4);fine=knee_points(mu,bsat,6)
            self.assertTrue(set(coarse).issubset(set(fine)))
            b,h=np.array(fine).T
            np.testing.assert_allclose(b,MU0*h+np.minimum(MU0*(mu-1)*h,bsat),atol=1e-12,rtol=1e-12)
            self.assertTrue(np.all(np.diff(h)>0))

    def test_unity_does_not_pass_merely_because_total_error_is_below_five_percent(self):
        difference,tolerance=factor_errors([1,1],[1.004,1.06])
        self.assertTrue(np.all(difference>tolerance))

    def test_absolute_floor_and_relative_added_factor_are_explicit(self):
        _,tolerance=factor_errors([1.004,1.35],[1.004,1.35])
        np.testing.assert_allclose(tolerance,[0.001,0.0175])
        with self.assertRaises(ValueError):factor_errors([1,float('nan')],[1,1.1])


if __name__=='__main__':
    unittest.main()
