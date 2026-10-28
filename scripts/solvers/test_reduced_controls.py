import copy
import unittest

from compare_reduced_fields import validate_controls


class ReducedControlsTest(unittest.TestCase):
    def test_mesh_far_and_domain_axes_cannot_be_combined(self):
        base={'model':{'source':1},'linear_material':False,'mesh_m':.0008,'gap_mesh_m':.0001,
            'observation_mesh_m':.0008,'physical_observation_band_m':.001,'far_mesh_m':.01,
            'air_radius_m':.06,'z_stretch':4,'quarter_symmetry':True}
        near=dict(base,mesh_m=.0006,gap_mesh_m=.000075,observation_mesh_m=.0006)
        far=dict(base,far_mesh_m=.008);domain=dict(base,air_radius_m=.075)
        for kind,case in [('mesh',near),('far',far),('domain',domain)]:validate_controls(base,case,kind)
        with self.assertRaises(ValueError):validate_controls(base,dict(near,far_mesh_m=.008),'mesh')
        with self.assertRaises(ValueError):validate_controls(base,dict(far,air_radius_m=.075),'far')
        bad=copy.deepcopy(near);bad['model']['source']=2
        with self.assertRaises(ValueError):validate_controls(base,bad,'mesh')
