import importlib.util
import unittest

import numpy as np

from finite_copper_primal import solve


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class PrimalDCCheckTest(unittest.TestCase):
    def test_annulus_matches_dc_analytic_power_and_mean_current(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry
        inner=.001;outer=.002;height=.0005
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        ring.mat('copper');mesh=ng.Mesh(OCCGeometry(ring).GenerateMesh(maxh=.00025));mesh.Curve(2)
        electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*(ng.x**2+ng.y**2))
        _,metadata=solve(ng,mesh,electric,1.)
        self.assertLess(abs(metadata['source_power_w']/(height*np.log(outer/inner)/(2*np.pi))-1),.02)
        self.assertLess(metadata['net_current_relative_error'],1e-9)
