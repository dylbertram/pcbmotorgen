import importlib.util
import unittest

import numpy as np

from ngsolve_periodic_ac import source_modes,energy,tensor,structured_mesh,symmetric_triangle_rule
from vector_harmonic_screen import source


class PeriodicSourceTest(unittest.TestCase):
    def test_rectangular_magnet_coefficients_match_independent_source_kernel(self):
        k,b=source_modes(9)
        expected=[source(float(wave),int(n)) for wave,n in zip(k,np.arange(1,18,2))]
        np.testing.assert_allclose(b,expected,rtol=1e-13,atol=1e-15)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class PeriodicFEConstitutiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ngsolve as ng
        from netgen.geom2d import unit_square
        cls.ng=ng;cls.mesh=ng.Mesh(unit_square.GenerateMesh(maxh=.5))

    def scalar(self,value):return float(self.ng.Integrate(value,self.mesh))

    def test_tensor_matches_energy_second_differences_on_both_material_branches(self):
        ng=self.ng
        for x,z in [(.02,.03),(.6,.3)]:
            h=1e-5
            e=lambda a,b:self.scalar(energy(ng,ng.CoefficientFunction(a),ng.CoefficientFunction(b),2500.,.45))
            centre=e(x,z)
            xx=(e(x+h,z)-2*centre+e(x-h,z))/h**2
            zz=(e(x,z+h)-2*centre+e(x,z-h))/h**2
            xz=(e(x+h,z+h)-e(x+h,z-h)-e(x-h,z+h)+e(x-h,z-h))/(4*h**2)
            actual=[self.scalar(v) for v in tensor(ng,ng.CoefficientFunction(x),ng.CoefficientFunction(z),2500.,.45)]
            np.testing.assert_allclose(actual,[xx,xz,zz],rtol=1e-5,atol=.01)

    def test_generated_mesh_has_periodic_identifications_and_internal_source(self):
        ng=self.ng;mesh=structured_mesh(ng,8,.002,4,4,2,.01,4)
        regular=ng.H1(mesh,order=2);periodic=ng.Periodic(regular)
        self.assertLess(sum(periodic.FreeDofs()),sum(regular.FreeDofs()))
        self.assertAlmostEqual(float(ng.Integrate(ng.CoefficientFunction(1.),mesh,definedon=mesh.Boundaries('source'))),.012,places=12)

    def test_triangle_rule_preserves_weight_degree_and_coordinate_symmetry(self):
        rule=symmetric_triangle_rule(self.ng,8)
        self.assertAlmostEqual(sum(p.weight for p in rule),.5,places=13)
        self.assertAlmostEqual(sum(p.weight*p.point[0]**2*p.point[1] for p in rule),1/60,places=13)
        # This nonsmooth antisymmetric integrand is not a polynomial exactness
        # check. It needs closure under permutation, as does the material knee.
        error=sum(p.weight*(max(p.point[0]-.27,0)-max(p.point[1]-.27,0)) for p in rule)
        self.assertAlmostEqual(error,0.,places=14)
