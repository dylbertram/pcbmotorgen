import unittest

import numpy as np

from cut_surface_force import box_force as affine_force, reflected_tetrahedra
from test_cut_surface_force import cube_tetrahedra
from total_field_stress import box_force


class TotalFieldStressTest(unittest.TestCase):
    def test_nonlinear_source_quadrature_preserves_xy_mirror_symmetry(self):
        vertices=cube_tetrahedra(0,1)
        vertices,reaction=reflected_tetrahedra(vertices,np.zeros_like(vertices))
        def source(points):
            x,y,z=points.T
            # Gradient of the harmonic potential (x^2+y^2)z - 2z^3/3.
            return np.column_stack([2*x*z,2*y*z,x*x+y*y-2*z*z])
        for depth in [0,1,2]:
            result=box_force(vertices,reaction,[-.5,-.4,.1],[.5,.4,.7],source,depth)
            np.testing.assert_allclose(result['force_n'][:2],0,atol=1e-8)

    def test_affine_source_plus_reaction_matches_exact_stress(self):
        vertices=cube_tetrahedra();reaction=vertices*[1.,2.,3.]+[1.,0.,0.]
        source=lambda p:p*[2.,3.,4.]+[0.,1.,0.]
        exact=affine_force(vertices,reaction+source(vertices.reshape(-1,3)).reshape(vertices.shape),[-.5]*3,[.5]*3)
        for depth in [0,1,2]:
            actual=box_force(vertices,reaction,[-.5]*3,[.5]*3,source,depth)
            np.testing.assert_allclose(actual['force_n'],exact['force_n'],rtol=1e-12,atol=1e-7)
            for face in actual['faces']:
                np.testing.assert_allclose(actual['faces'][face]['force_n'],exact['faces'][face]['force_n'],rtol=1e-12,atol=1e-7)

    def test_invalid_coverage_source_and_quadrature_are_rejected(self):
        v=cube_tetrahedra();b=np.zeros_like(v);source=lambda p:np.zeros_like(p)
        with self.assertRaises(ValueError):box_force(v[:1],b[:1],[-.5]*3,[.5]*3,source,0)
        with self.assertRaises(ValueError):box_force(v,b,[-.5]*3,[.5]*3,source,True)
        with self.assertRaises(ValueError):box_force(v,b,[-.5]*3,[.5]*3,lambda p:p*float('nan'),0)
