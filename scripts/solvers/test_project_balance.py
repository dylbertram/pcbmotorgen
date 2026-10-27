import unittest

import numpy as np

from post_project_balance import action_reaction,surfaces


class ProjectBalanceTest(unittest.TestCase):
    def test_force_reaction_is_checked_not_imposed(self):
        self.assertTrue(action_reaction([0,0,1],[0,0,-1.01])['passed'])
        self.assertFalse(action_reaction([0,0,1],[0.1,0,-1])['passed'])
        with self.assertRaises(ValueError):action_reaction([0,0,float('nan')],[0,0,-1])
        with np.errstate(over='ignore'),self.assertRaises(ValueError):action_reaction([0,0,1e300],[0,0,-1e300])

    def test_mover_surface_respects_its_physical_pose_and_outer_clearance(self):
        obj={'origin_m':[0.01,0.002,0.001],'size_m':[0.005,0.005,0.003]}
        faces=surfaces([obj],0.0001,4,0.06)
        points=np.concatenate([p for p,_,_ in faces])
        np.testing.assert_allclose(points.min(axis=0),[0.0099,0.0019,0.0009],atol=1e-15)
        np.testing.assert_allclose(points.max(axis=0),[0.0151,0.0071,0.0041],atol=1e-15)
        with self.assertRaises(ValueError):surfaces([obj],0.0001,4,0.01)


if __name__=='__main__':unittest.main()
