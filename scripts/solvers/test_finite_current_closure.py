import importlib.util
import unittest

import numpy as np

from finite_current_closure import solve,rectangle_gradient_loss


class RectangleGradientTest(unittest.TestCase):
    def test_long_slab_limit_and_scaling(self):
        result=rectangle_gradient_loss([100.,1.,.1],1.,1.)
        self.assertLess(abs(result/(100*.1/12)-1),.01)
        self.assertAlmostEqual(rectangle_gradient_loss([1.,2.,.1],2.,-3.),
            18*rectangle_gradient_loss([2.,1.,.1],1.,1.))


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class FiniteCurrentClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        cls.ng=ng
        cls.mesh=ng.Mesh(OCCGeometry(Box(Pnt(0,0,0),Pnt(1,1,.1))).GenerateMesh(maxh=.3))

    def test_uniform_translation_is_cancelled_by_electric_potential(self):
        result=solve(self.ng,self.mesh,self.ng.CoefficientFunction((0.,0.,.2)),1.,1.)
        self.assertLess(result['equation_relative_residual'],1e-9)
        self.assertLess(result['joule_power_w'],1e-20)

    def test_nonuniform_field_is_passive_and_respects_speed_parity(self):
        ng=self.ng;field=ng.CoefficientFunction((ng.z,0.,ng.x))
        forward=solve(ng,self.mesh,field,1.,1.);reverse=solve(ng,self.mesh,field,1.,-1.)
        self.assertGreater(forward['joule_power_w'],0.)
        self.assertLess(forward['housing_force_n'][0],0.)
        self.assertLess(forward['mechanical_joule_relative_balance'],1e-9)
        exact=rectangle_gradient_loss([1.,1.,.1],1.,1.)
        self.assertLess(abs(forward['joule_power_w']/exact-1),.02)
        np.testing.assert_allclose(forward['housing_force_n'],-np.array(reverse['housing_force_n']),rtol=1e-10,atol=1e-14)
        np.testing.assert_allclose(forward['net_volume_current_a_m'],0.,atol=1e-12)
