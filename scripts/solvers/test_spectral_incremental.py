import unittest

import numpy as np

from spectral_incremental import FullPhasePlate, response


class IncrementalTensorTest(unittest.TestCase):
    def test_saturated_bias_is_directional_and_matches_nonlinear_perturbations(self):
        result=response(0.0002,130,0.25,cells=8,modes=3,samples=128)
        r0,r90=result['fundamental_reflection_per_phase']
        self.assertGreater(r0,0)
        self.assertGreater(r90,10*r0)
        self.assertGreater(result['quadrature_saturated_fraction'],0)
        self.assertLessEqual(result['quadrature_saturated_fraction'],1)
        for perturbation in result['finite_differences']:
            self.assertLess(max(perturbation['absolute_reflection_error']),1e-6)

    def test_both_spatial_phases_recover_the_same_linear_slab_reflection(self):
        mu=130;t=0.001;k=np.pi/0.006;rho=(mu-1)/(mu+1)
        expected=rho*(1-np.exp(-2*k*t))/(1-rho*rho*np.exp(-2*k*t))
        result=response(t,mu,1000,cells=16,modes=3,samples=128)
        np.testing.assert_allclose(result['fundamental_reflection_per_phase'],expected,rtol=1e-4)
        self.assertEqual(result['quadrature_saturated_fraction'],0)
        self.assertEqual(len(result['finite_differences']),2)

    def test_extended_phase_hessian_is_the_true_energy_jacobian(self):
        plate=FullPhasePlate(0.001,130,0.25,4,3,128)
        vector=plate.initial();_,gradient,matrix=plate.evaluate(vector)
        direction=np.random.default_rng(5).normal(size=len(vector))*1e-5;eps=1e-5
        plus=plate.evaluate(vector+eps*direction,hessian=False)[1]
        minus=plate.evaluate(vector-eps*direction,hessian=False)[1]
        np.testing.assert_allclose((plus-minus)/(2*eps),matrix@direction,rtol=1e-6,atol=1e-6)
        np.testing.assert_allclose(matrix.toarray(),matrix.toarray().T,atol=1e-7)


if __name__=='__main__':
    unittest.main()
