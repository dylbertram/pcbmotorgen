import itertools
import unittest

import numpy as np

from cut_surface_force import MU0,box_force,reflected_tetrahedra


def cube_tetrahedra(lower=-1.,upper=1.):
    cells=[]
    for permutation in itertools.permutations(range(3)):
        points=[np.zeros(3)];p=np.zeros(3)
        for i in permutation:
            p=p.copy();p[i]=1.;points.append(p)
        cells.append(np.asarray(points)*(upper-lower)+lower)
    return np.asarray(cells)


class CutSurfaceForceTest(unittest.TestCase):
    def test_constant_field_has_zero_closed_force_and_exact_individual_traction(self):
        vertices=cube_tetrahedra();field=np.broadcast_to([1.,2.,3.],vertices.shape)
        result=box_force(vertices,field,[-0.7,-0.6,-0.5],[0.4,0.3,0.2])
        np.testing.assert_allclose(result['force_n'],0,atol=2e-8)
        face=result['faces']['0/1'];expected=np.array([-6.,2.,3.])*0.9*0.7/MU0
        np.testing.assert_allclose(face['force_n'],expected,rtol=1e-12)

    def test_affine_field_stress_is_integrated_to_roundoff(self):
        vertices=cube_tetrahedra();field=vertices*np.array([1.,2.,3.])+[1.,0.,0.]
        result=box_force(vertices,field,[-0.5]*3,[0.5]*3)
        # For this curl-free affine test field, div(T) = B div(B)/mu0.
        # div(B)=6, volume=1, mean B=(1,0,0), an analytic degree-two test.
        np.testing.assert_allclose(result['force_n'],[6/MU0,0,0],rtol=1e-12,atol=2e-8)

    def test_coincident_tetra_faces_are_not_counted_twice(self):
        # Box cuts coincide with mesh faces and the outer mesh boundary.
        vertices=cube_tetrahedra();field=np.ones_like(vertices)
        result=box_force(vertices,field,[-1.]*3,[1.]*3)
        np.testing.assert_allclose(result['force_n'],0,atol=2e-8)
        for face in result['faces'].values():self.assertAlmostEqual(face['area_m2'],4.)

    def test_missing_or_duplicated_surface_coverage_is_rejected(self):
        vertices=cube_tetrahedra();field=np.ones_like(vertices)
        with self.assertRaises(ValueError):box_force(vertices[:1],field[:1],[-0.5]*3,[0.5]*3)
        with self.assertRaises(ValueError):box_force(np.repeat(vertices,2,axis=0),np.repeat(field,2,axis=0),[-0.5]*3,[0.5]*3)
        with self.assertRaises(ValueError):box_force(vertices,field,[-0.5]*3,[float('nan')]*3)

    def test_quarter_reconstructs_signed_fields_not_a_scaled_force(self):
        vertices=cube_tetrahedra(0,1);field=vertices*np.array([1.,2.,3.])
        full,vectors=reflected_tetrahedra(vertices,field)
        result=box_force(full,vectors,[-0.5,-0.5,0.1],[0.5,0.5,0.7])
        # mean Bz=1.2, div B=6, volume=.6.
        np.testing.assert_allclose(result['force_n'],[0,0,6*1.2*0.6/MU0],rtol=1e-12,atol=2e-8)
        with self.assertRaises(ValueError):reflected_tetrahedra(-vertices,field)


if __name__=='__main__':unittest.main()
