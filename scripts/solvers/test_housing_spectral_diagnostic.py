import unittest

import numpy as np

from check_housing_motion_reference import case_base, reference
from housing_spectral_diagnostic import harmonic_power


class HousingSpectralDiagnosticTest(unittest.TestCase):
    def test_fundamental_reproduces_independent_p1_definition(self):
        case=case_base()
        np.testing.assert_allclose(harmonic_power(case,1,cells=48,samples=128),reference(case,48,samples=128)['regions_w'],rtol=1e-12,atol=1e-12)

    def test_zero_reverse_and_remanence_square_scaling(self):
        case=case_base();forward=np.array(harmonic_power(case,3,cells=24,samples=64))
        case['speed_m_s']*=-1
        np.testing.assert_allclose(harmonic_power(case,3,cells=24,samples=64),forward,rtol=1e-12)
        case['sim']['magnet_remanence_t']*=2
        np.testing.assert_allclose(harmonic_power(case,3,cells=24,samples=64),4*forward,rtol=1e-12)
        case['speed_m_s']=0
        self.assertEqual(harmonic_power(case,3,cells=24,samples=64),[0.,0.])

    def test_rejects_unqualified_magnetic_linearization(self):
        case=case_base();case['sim']['backplane']['layers']=[{'material':'flex_ferrite','thickness_m':.0002}]
        with self.assertRaises(ValueError):harmonic_power(case,1)

    def test_rejects_invalid_numerical_controls(self):
        for kwargs in [{'harmonic':0},{'harmonic':2},{'harmonic':1,'samples':3},{'harmonic':1,'cutoff':float('inf')}]:
            with self.assertRaises(ValueError):harmonic_power(case_base(),**kwargs)
