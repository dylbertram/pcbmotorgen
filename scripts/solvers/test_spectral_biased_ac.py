import cmath
import unittest

import numpy as np

from spectral_biased_ac import bias_state, complex_response
from spectral_plate import MU0
from spectral_incremental import response


def exact_reflection(k,frequency,layers):
    below=k;g=0j;omega=2*np.pi*frequency
    for t,mu,sigma in reversed(layers):
        gamma=cmath.sqrt(k*k+1j*omega*MU0*mu*sigma);eta=gamma/mu
        rho=(eta-below)/(eta+below)
        g=(rho+g)/(1+rho*g)*cmath.exp(-2*gamma*t);below=eta
    rho=(k-below)/(k+below)
    return (rho+g)/(1+rho*g)


class BiasedAcLinearLimitTest(unittest.TestCase):
    def test_saturated_tensor_recovers_dc_limit_and_passive_ac_loss(self):
        plate,matrix,_=bias_state(0.0002,130,0.25,8,3,128)
        dc=complex_response(plate,matrix,0)
        expected=response(0.0002,130,0.25,8,3,128,finite_differences=False)
        np.testing.assert_allclose(np.array(dc['reflection_per_phase'])[:,0],expected['fundamental_reflection_per_phase'],atol=5e-5,rtol=1e-4)
        ac=complex_response(plate,matrix,100e3)
        self.assertTrue(all(v>0 for v in ac['joule_coefficient_w_m2_t2']))
        self.assertTrue(all(v[1]<0 for v in ac['reflection_per_phase']))

    def test_linear_multilayer_skin_limit_and_power_balance(self):
        plate,matrix,_=bias_state(0.0002,130,1000,16,3,128)
        result=complex_response(plate,matrix,100e3)
        expected=exact_reflection(np.pi/0.006,100e3,[(0.0002,130,0),(0.0001,1,0),(0.001,1,25e6)])
        reflection=np.array([complex(*v) for v in result['reflection_per_phase']])
        np.testing.assert_allclose(reflection,expected,rtol=5e-4,atol=1e-5)
        np.testing.assert_allclose(result['joule_coefficient_w_m2_t2'],result['source_work_coefficient_w_m2_t2'],rtol=1e-8)

    def test_zero_frequency_and_invalid_conductivity(self):
        plate,matrix,_=bias_state(0.0002,130,1000,8,3,128)
        result=complex_response(plate,matrix,0)
        np.testing.assert_array_equal(result['joule_coefficient_w_m2_t2'],0)
        self.assertTrue(all(abs(v[1])<1e-10 for v in result['reflection_per_phase']))
        with self.assertRaises(ValueError):complex_response(plate,matrix,100e3,conductivity=-1)


if __name__=='__main__':
    unittest.main()
