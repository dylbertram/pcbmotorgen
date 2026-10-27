import unittest

import numpy as np

from finite_copper_drive_profile import electric
from finite_copper_current import solve


class DriveGaugeControlTest(unittest.TestCase):
    def test_analytic_profile_is_unit_emf_and_zero_end_gradient_shift(self):
        profile=np.polynomial.Polynomial([0.,6.,-6.]);shift=profile.integ()-np.polynomial.Polynomial([0.,1.])
        self.assertAlmostEqual(profile.integ()(1.)-profile.integ()(0.),1.)
        self.assertAlmostEqual(shift(0.),0.);self.assertAlmostEqual(shift(1.),0.)
        self.assertEqual(list(shift.coef),[0.,-1.,3.,-2.])

    def test_full_compatible_current_invariant_on_identical_ring_mesh(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,Box,Glue,OCCGeometry
        whole=Cylinder(Pnt(0,0,0),Dir(0,0,1),.002,.0005)-Cylinder(Pnt(0,0,0),Dir(0,0,1),.001,.0005)
        drive=whole*Box(Pnt(0.,-.0002,0.),Pnt(.003,.0002,.0005));rest=whole-drive
        drive.mat('drive');rest.mat('copper');mesh=ng.Mesh(OCCGeometry(Glue([rest,drive])).GenerateMesh(maxh=.0004));mesh.Curve(1)
        uniform=mesh.MaterialCF({'drive':ng.CoefficientFunction((0.,2500.,0.))},default=ng.CoefficientFunction((0.,0.,0.)))
        a,_=solve(ng,mesh,uniform,1.)
        b,_=solve(ng,mesh,electric(ng,mesh,[[.0015,-.0002,.00025],[.0015,.0002,.00025]]),1.)
        delta=b.components[0]-a.components[0]
        reference=float(ng.Integrate(ng.InnerProduct(a.components[0],a.components[0]),mesh,order=6))
        error=float(ng.Integrate(ng.InnerProduct(delta,delta),mesh,order=6))
        self.assertLess(np.sqrt(error/reference),1e-8)
