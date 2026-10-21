import unittest

import numpy as np

from ngsolve_winding_static import line_samples
from pm_current_force import array_force
from wire_pm_linkage import linkage,position_gradient


class ReciprocalPMLinkageTest(unittest.TestCase):
    def setUp(self):
        path=np.array([[-.004,-.004,0.],[.004,-.004,0.],[.004,.004,0.],[-.004,.004,0.],[-.004,-.004,0.]])
        self.segments=np.stack([path[:-1],path[1:]],axis=1);self.currents=np.ones(4)
        self.magnets=[{'origin_m':[.001,-.001,.003],'size_m':[.002,.002,.002],'polarization_t':[0.,0.,1.34]}]

    def test_linkage_derivative_recovers_independent_pm_force_not_negative_copper_force(self):
        gradient=position_gradient(self.magnets,self.segments,self.currents,10,1e-7)
        points,dl=line_samples(self.segments,self.currents,100)
        independent=array_force(self.magnets,points,dl).sum(axis=0)
        np.testing.assert_allclose(gradient,independent,rtol=1e-3,atol=1e-10)

    def test_volume_order_and_current_sign_are_explicit(self):
        first=linkage(self.magnets,self.segments,self.currents,8);second=linkage(self.magnets,self.segments,self.currents,12)
        self.assertAlmostEqual(first/second,1.,places=7)
        self.assertAlmostEqual(linkage(self.magnets,self.segments,-self.currents,12),-second,places=14)
        with self.assertRaises(ValueError):linkage(self.magnets,self.segments,self.currents,1)
