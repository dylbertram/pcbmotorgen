import unittest

import numpy as np

from spectral_plate import Plate, constitutive, solve, MU0
from vector_harmonic_screen import source


class SpectralEnergyTest(unittest.TestCase):
    def test_linear_slab_has_the_exact_air_reflection_limit(self):
        t=0.001;mu=130;k=np.pi/0.006;rho=(mu-1)/(mu+1)
        reflection=rho*(1-np.exp(-2*k*t))/(1-rho*rho*np.exp(-2*k*t))
        result=solve(t,mu,1000,32,1,128)
        bn=source(k,1)
        self.assertLess(abs(result['pressure_pa']/(bn*bn*reflection/MU0*0.006/0.005)-1),1e-4)
        self.assertLess(abs(result['field_ratio']/(1+reflection*np.exp(-2*k*0.0008))-1),1e-4)

    def test_constitutive_tensor_is_energy_derivative_and_positive(self):
        x=np.array([0.01,0.2,0.3]);z=np.array([0.02,0.25,0.4])
        w,hx,hz,dxx,dxz,dzz=constitutive(x,z,130,0.25)
        eps=1e-7
        plus=constitutive(x+eps,z,130,0.25);minus=constitutive(x-eps,z,130,0.25)
        np.testing.assert_allclose((plus[0]-minus[0])/(2*eps),hx,rtol=1e-8)
        np.testing.assert_allclose((plus[1]-minus[1])/(2*eps),dxx,rtol=1e-8)
        np.testing.assert_allclose((plus[2]-minus[2])/(2*eps),dxz,rtol=1e-8)
        self.assertTrue(np.all(dxx*dzz-dxz*dxz>0))
        self.assertAlmostEqual(dxx[0],1/(MU0*130))

    def test_global_gradient_hessian_and_boundary_terms(self):
        plate=Plate(0.001,130,0.25,4,3,128)
        vector=plate.initial();energy,gradient,matrix=plate.evaluate(vector)
        direction=np.random.default_rng(42).normal(size=len(vector))*1e-5
        eps=1e-5
        plus=plate.evaluate(vector+eps*direction,hessian=False)
        minus=plate.evaluate(vector-eps*direction,hessian=False)
        self.assertAlmostEqual((plus[0]-minus[0])/(2*eps),gradient@direction,delta=1e-8)
        np.testing.assert_allclose((plus[1]-minus[1])/(2*eps),matrix@direction,rtol=2e-7,atol=1e-7)
        np.testing.assert_allclose(matrix.toarray(),matrix.toarray().T,atol=1e-7)
        self.assertGreater(np.min(np.linalg.eigvalsh(matrix.toarray())),0)


if __name__=='__main__':
    unittest.main()
