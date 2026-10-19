import unittest

import numpy as np

from audit_project_bare_map import compare,observations
from test_mesh_stretch import model


class BareMapTest(unittest.TestCase):
    def test_midpoint_map_does_not_hide_both_transverse_components_on_mirror_planes(self):
        planes=observations(model(),64,24)
        self.assertEqual(len(planes),3)
        for points in planes.values():
            self.assertEqual(points.shape,(64*24,3))
            self.assertTrue(np.all(abs(points[:,:2])>1e-14))
            self.assertTrue(np.all(points[:,2]<0.0013))
        with self.assertRaises(ValueError):observations(model(),0,24)

    def test_above_planes_use_top_bounds_and_leave_lower_planes_unchanged(self):
        physical=model();below=observations(physical,64,24);both=observations(physical,64,24,True)
        top=max(m['origin_m'][2]+m['size_m'][2] for m in physical['magnets'])
        self.assertEqual(len(both),6)
        for clearance,points in below.items():
            np.testing.assert_array_equal(both[clearance],points)
            above=both['above:'+clearance]
            np.testing.assert_array_equal(above[:,:2],points[:,:2])
            np.testing.assert_allclose(above[:,2],top+float(clearance))

    def test_full_vector_gate_includes_transverse_error_and_rejects_nan(self):
        self.assertTrue(compare([[0,0,1.01]],[[0,0,1]])['passed'])
        self.assertFalse(compare([[0,0.06,1]],[[0,0,1]])['passed'])
        with self.assertRaises(ValueError):compare([[0,0,float('nan')]],[[0,0,1]])
        with self.assertRaises(ValueError):compare([[0,0,0]],[[0,0,0]])
