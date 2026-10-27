import unittest

import magpylib as magpy
import numpy as np
from numpy.polynomial.legendre import leggauss

from material_source_field import dipole_field,exterior_points,MU0


class MaterialExteriorFieldTest(unittest.TestCase):
    def test_prescribed_uniform_cuboid_matches_independent_charge_kernel(self):
        x,w=leggauss(10);a,b,c=np.meshgrid(x,x,x,indexing='ij');points=np.column_stack([a.ravel(),b.ravel(),c.ravel()])*.001
        volume=np.einsum('i,j,k->ijk',w,w,w).ravel()*1e-9;magnetization=np.array([1e5,2e5,3e5])
        moments=volume[:,None]*magnetization;observations=np.array([[.003,.002,.004],[-.004,.001,.003],[.002,-.005,.004]])
        expected=magpy.magnet.Cuboid(dimension=[.002]*3,polarization=MU0*magnetization).getB(observations)
        np.testing.assert_allclose(dipole_field(observations,points,moments,2),expected,rtol=1e-8,atol=1e-12)

    def test_inside_material_and_point_self_observations_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Singular'):dipole_field([[0.,0.,0.]],[[0.,0.,0.]],[[0.,0.,1.]])
        model={'stack':[{'mu_r':130.,'origin_m':[0.,0.,0.],'size_m':[1.,1.,1.]}]}
        with self.assertRaisesRegex(ValueError,'inside/on'):exterior_points(model,np.array([[.5,.5,.5]]))
