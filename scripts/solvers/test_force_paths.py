import unittest

import numpy as np

from force_paths import force_paths
from post_project_balance import bounds
from test_mesh_stretch import model


class ForcePathsTest(unittest.TestCase):
    def test_original_near_surface_paths_are_unchanged(self):
        physical=model();lower,upper=bounds(physical['magnets'])
        for key,(low,high) in force_paths(physical,'mover').items():
            np.testing.assert_array_equal(low,lower-float(key))
            np.testing.assert_array_equal(high,upper+float(key))

    def test_remote_paths_enclose_each_body_but_not_the_other(self):
        physical=model();gap_lower=bounds(physical['stack'])[1][2];gap_upper=bounds(physical['magnets'])[0][2]
        for name,objects in [('stator',physical['stack']),('mover',physical['magnets'])]:
            lower,upper=bounds(objects)
            for key,(low,high) in force_paths(physical,name,True).items():
                self.assertTrue(np.all(low<lower));self.assertTrue(np.all(high>upper))
                plane=low[2] if name=='mover' else high[2]
                self.assertGreater(plane,gap_lower);self.assertLess(plane,gap_upper)
                self.assertGreaterEqual(lower[0]-low[0],0.001-1e-15)
                self.assertAlmostEqual(plane,gap_lower+[0.35,0.5,0.65][int(key)]*(gap_upper-gap_lower))

    def test_overlapping_or_missing_bodies_are_not_force_paths(self):
        physical=model();physical['magnets'][0]['origin_m'][2]=-1
        with self.assertRaises(ValueError):force_paths(physical,'mover',True)
        with self.assertRaises(ValueError):force_paths(model(),'unknown')
