import unittest
import tempfile
from pathlib import Path
import numpy as np

from sample_dc_winding_field import observations,integrate,bound_declaration
from audit_dc_case_matrix import Evidence


class QualifiedWindingFieldTest(unittest.TestCase):
    def test_hash_bound_physical_declaration_is_not_a_numerical_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'physical.json';path.write_text('{"closure":{}}');evidence=Evidence()
            with self.assertRaises(ValueError):bound_declaration(evidence,path)
            evidence.digest(path);self.assertEqual(bound_declaration(evidence,path),{'closure':{}})
            path.write_text('{"changed":true}')
            with self.assertRaises(ValueError):bound_declaration(evidence,path)

    def test_declared_grid_has_native_xyz_order_and_bounded_cost(self):
        grid=observations(dict(bounds_m=[[0,.01],[-.002,.003],[-.003,-.001]],counts=[8,3,4]))
        self.assertEqual(grid.shape,(96,3));np.testing.assert_allclose(grid[8],[0,.0005,-.003])
        for count in [[20,5,7],[1,3,4],[True,3,4],[8,3,5]]:
            with self.assertRaises(ValueError):observations(dict(bounds_m=[[0,1]]*3,counts=count))
        with self.assertRaises(ValueError):observations(dict(bounds_m=[[0,float('nan')]]*3,counts=[2,2,2]))

    def test_own_basis_normalization_zero_and_signed_current_not_pm_or_rms_scaling(self):
        cells=np.asarray([[[0,0,0],[.001,0,0],[0,.001,0],[0,0,.001]]])
        mean=np.asarray([[2.,0,0]]);slope=np.asarray([.1]);points=np.asarray([[.002,.002,.002]])
        a=integrate(points,cells,mean,slope,.2,.1)
        np.testing.assert_allclose(integrate(points,cells,mean,slope,.2,-.1),-a)
        np.testing.assert_allclose(integrate(points,cells,mean,slope,.2,.5),5*a)
        np.testing.assert_array_equal(integrate(points,cells,mean,slope,.2,0.),np.zeros((1,3)))
        with self.assertRaises(ValueError):integrate(np.asarray([[.0001,.0001,.0001]]),cells,mean,slope,.2,0.)
        with self.assertRaises(ValueError):integrate(points,cells,mean,slope,0.,.1)
