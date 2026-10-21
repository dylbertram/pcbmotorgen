import copy
import unittest

from audit_winding_reciprocity import pose_model


class WindingPoseIsolationTest(unittest.TestCase):
    def fixtures(self):
        names=['closed_wire_source.py','vector_material.py','pm_current_force.py','quadrature_source.py','ngsolve_material_motion.py']
        base={'model':{'magnets':[{'origin_m':[0.,0.,.0013]}],'array_centre_mm':[0.,0.],
            'stack':[{'origin_m':[0.,0.,-.0002]}]},'translation_m':[-.0534,-.004,.0008],
            'closure':{'return_path_m':[[0.,0.,0.],[0.,0.,.001]]},'mesh_sha256':'same',
            'source_snapshots':{name:{'sha256':name} for name in names}}
        posed=copy.deepcopy(base);posed['model']['magnets'][0]['origin_m'][0]+=.0001
        posed['model']['array_centre_mm'][0]+=.1;posed['source_pose_offset_m']=[.0001,0.,0.]
        return base,posed

    def test_only_pm_moves_not_ferrite_copper_or_return(self):
        base,posed=self.fixtures();pose_model(base,posed,.0001)
        for field in ['model','translation_m','closure']:
            _,changed=self.fixtures()
            if field=='model':changed['model']['stack'][0]['origin_m'][0]+=.0001
            elif field=='translation_m':changed[field][0]+=.0001
            else:changed[field]['return_path_m'][1][2]+=.0001
            with self.assertRaises(ValueError):pose_model(base,changed,.0001)

    def test_source_or_constitutive_change_cannot_hide_in_pose_difference(self):
        base,posed=self.fixtures();posed['source_snapshots']['vector_material.py']['sha256']='changed'
        with self.assertRaisesRegex(ValueError,'definitions differ'):pose_model(base,posed,.0001)
