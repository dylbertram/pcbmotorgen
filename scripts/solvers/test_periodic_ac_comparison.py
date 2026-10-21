import unittest

import numpy as np

from compare_periodic_ac import fe_observables
from audit_biased_ac import changes


class PeriodicACComparisonTest(unittest.TestCase):
    def test_added_reactive_gate_retains_the_existing_absolute_floor(self):
        first=(np.array([[1.001,0.],[1.8,-.002]]),np.array([2.,3.]))
        second=(np.array([[1.,0.],[1.8,-.002]]),np.array([2.,3.]))
        self.assertTrue(changes(first,second,relative=.05)['passed'])
        first[0][0,0]=1.0011
        self.assertFalse(changes(first,second,relative=.05)['passed'])

    def test_free_space_green_response_is_unit_coil_factor(self):
        data={'ac':[{'reflection':[0.,0.],'joule_coefficient_w_m2_t2':1.},
                    {'reflection':[0.,0.],'joule_coefficient_w_m2_t2':2.}]}
        factors,loss=fe_observables(data)
        np.testing.assert_array_equal(factors,[[1.,0.],[1.,0.]])
        np.testing.assert_array_equal(loss,[1.,2.])
        data['ac'][0]['joule_coefficient_w_m2_t2']=float('nan')
        with self.assertRaises(ValueError):fe_observables(data)
