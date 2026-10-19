import copy
import unittest

from audit_project_symmetry import match_settings,vector_errors


class SymmetryAuditTest(unittest.TestCase):
    def test_mesh_and_physics_changes_cannot_be_hidden_as_symmetry_parity(self):
        full={'backend':'getdp','model':{'source':'same'},'mesh_m':0.001,'gap_mesh_m':0.0001,'air_radius_m':0.03}
        quarter={**copy.deepcopy(full),'quarter_symmetry':True}
        match_settings(full,quarter)
        for key,value in [('mesh_m',0.0005),('model',{'source':'different'}),('quarter_symmetry',False),('z_stretch',4),('far_mesh_m',0.002),('magnet_face_mesh_m',0.0001),('magnet_face_band_m',0.0004)]:
            bad=copy.deepcopy(quarter);bad[key]=value
            with self.assertRaises(ValueError):match_settings(full,bad)

    def test_vector_parity_includes_lateral_force_and_absolute_near_zero_floor(self):
        self.assertTrue(vector_errors([[0,0,1]],[[0,0,1.01]],[[0,0,1]],[[0,0,1.01]])['passed'])
        self.assertFalse(vector_errors([[0,0,1]],[[0,0,1]],[[0,0,1]],[[0.03,0,1]])['passed'])
        self.assertTrue(vector_errors([[0,0,1]],[[0,0,1]],[[0,0,0]],[[0,0,1e-9]])['passed'])
        with self.assertRaises(ValueError):vector_errors([[0,0,float('nan')]],[[0,0,1]],[[0,0,1]],[[0,0,1]])


if __name__=='__main__':unittest.main()
