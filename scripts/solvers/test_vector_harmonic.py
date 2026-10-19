import math
import unittest

import numpy as np

from vector_harmonic_screen import projection, fields, harmonic_fields, harmonic_projection, MU0


class VectorProjectionTest(unittest.TestCase):
    def test_vectorized_modes_and_signed_linear_projection(self):
        k=math.pi/0.006;t=np.full(16,0.005/16);mu=np.full(16,130)
        harmonics=np.array([1,3,5]);incidents=np.array([0.001,-0.0002,0.00003])
        r,hx,hz=harmonic_fields(k*harmonics,t,mu,mu,incidents)
        for i,n in enumerate(harmonics):
            rr,x,z=fields(k*n,t,mu,mu,abs(incidents[i]))
            self.assertAlmostEqual(r[i],rr,places=14)
            np.testing.assert_allclose(hx[i],x*np.sign(incidents[i]),rtol=1e-13)
            np.testing.assert_allclose(hz[i],z*np.sign(incidents[i]),rtol=1e-13)
        x,z=harmonic_projection(130,0.25,hx,hz,harmonics,512)
        np.testing.assert_allclose([x,z],130,rtol=1e-13)

    def test_linear_and_circular_bias_limits(self):
        x,z=projection(130,0.25,[1],[2])
        np.testing.assert_allclose([x,z],130,rtol=1e-14)
        h=1e6;expected=1+0.25/(MU0*h)
        x,z=projection(130,0.25,[h],[h])
        np.testing.assert_allclose([x,z],expected,rtol=1e-14)

    def test_vector_projection_recovers_scalar_describing_function(self):
        mu=130;bsat=0.25;h=20000;x=bsat/(MU0*(mu-1)*h)
        expected=1+(mu-1)*2/math.pi*(math.asin(x)+x*math.sqrt(1-x*x))
        px,_=projection(mu,bsat,[h],[0],samples=32768)
        np.testing.assert_allclose(px,expected,rtol=1e-8)

    def test_anisotropic_layers_recover_isotropic_slab_and_refinement(self):
        k=math.pi/0.006;t=0.005;mu=130;rho=(mu-1)/(mu+1)
        expected=rho*(1-math.exp(-2*k*t))/(1-rho*rho*math.exp(-2*k*t))
        for n in [1,16]:
            r,hx,hz=fields(k,np.full(n,t/n),np.full(n,mu),np.full(n,mu))
            self.assertAlmostEqual(r,expected,places=13)
            self.assertTrue(np.isfinite(hx).all() and np.isfinite(hz).all())


if __name__=='__main__':
    unittest.main()
