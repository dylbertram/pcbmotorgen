import importlib.util
import unittest

import numpy as np

from vector_material import energy_b,h_b,magnetization_b,reduced_density,MU0
from spectral_plate import constitutive


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class VectorMaterialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ngsolve as ng
        from netgen.geom2d import unit_square
        cls.ng=ng;cls.mesh=ng.Mesh(unit_square.GenerateMesh(maxh=.5))

    def scalar(self,cf):return float(self.ng.Integrate(cf,self.mesh))

    def vector(self,cf):return np.asarray(self.ng.Integrate(cf,self.mesh),dtype=float)

    def test_three_dimensional_law_matches_the_qualified_radial_constitutive_law(self):
        ng=self.ng
        for values in [[.01,.02,.03],[.2,.3,.4]]:
            b=np.array(values);radius=np.linalg.norm(b);reference=constitutive(np.array([radius]),np.array([0.]),130.,.25)
            field=ng.CoefficientFunction(tuple(values))
            self.assertAlmostEqual(self.scalar(energy_b(ng,field,130.,.25))/reference[0][0],1.,places=11)
            np.testing.assert_allclose(self.vector(h_b(ng,field,130.,.25)),reference[1][0]*b/radius,rtol=1e-11)
            self.assertLessEqual(np.linalg.norm(self.vector(magnetization_b(ng,field,130.,.25))),.25/MU0*(1+1e-12))

    def test_energy_gradient_is_the_full_vector_h_field(self):
        ng=self.ng;b=np.array([.2,.3,.4]);delta=1e-6
        def value(point):return self.scalar(energy_b(ng,ng.CoefficientFunction(tuple(point)),130.,.25))
        finite=np.array([(value(b+np.eye(3)[i]*delta)-value(b-np.eye(3)[i]*delta))/(2*delta) for i in range(3)])
        np.testing.assert_allclose(finite,self.vector(h_b(ng,ng.CoefficientFunction(tuple(b)),130.,.25)),rtol=1e-8)

    def test_vacuum_source_transform_is_independent_of_the_particular_field(self):
        ng=self.ng;r=ng.CoefficientFunction((.01,-.02,.03));s=ng.CoefficientFunction((.2,.3,.4))
        actual=self.scalar(reduced_density(ng,r,s,1.,None))
        expected=(.01**2+.02**2+.03**2)/(2*MU0)
        self.assertAlmostEqual(actual/expected,1.,places=11)
