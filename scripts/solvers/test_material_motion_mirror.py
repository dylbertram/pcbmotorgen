import copy
import unittest

from audit_material_motion_mirror import symmetric_model, mirror_checks
from test_housing_model_scope import record as geometry_record
from test_material_motion_controls import record


def pair():
    first=record();model=geometry_record()['model'];model['stack']=[geometry_record()['housing']];first['model']=model
    first['request']['speed']=1.
    for i,row in enumerate(first['steps']):
        row.update(source_offset_m=(i+.5)*.0025,mechanical_source_work_w=1.001)
        row['material_source_force_n']=[.001,0.,100.]
    second=copy.deepcopy(first);second['request']['speed']=-1.
    second['profile']['end_offset_m']*=-1
    for row in second['steps']:
        row['source_offset_m']*=-1
        for field in ['housing_source_force_n','material_source_force_n']:row[field][0]*=-1
    return first,second


class MaterialMotionMirrorTest(unittest.TestCase):
    def test_symmetric_axial_source_is_accepted(self):
        model=geometry_record()['model'];model['stack']=[geometry_record()['housing']];symmetric_model(model)

    def test_asymmetric_material_or_magnet_is_rejected(self):
        for which in ['material','magnet','polarization']:
            model=copy.deepcopy(geometry_record()['model']);model['stack']=[geometry_record()['housing']]
            if which=='material':model['stack'][0]['origin_m'][0]+=.001
            elif which=='magnet':model['magnets'][0]['origin_m'][0]+=.001
            else:model['magnets'][0]['polarization_t']=[1.,0.,1.34]
            with self.assertRaises(ValueError):symmetric_model(model)

    def test_mirrored_forces_keep_normal_attraction_and_reverse_drag(self):
        first,second=pair();self.assertTrue(mirror_checks(first,second)['passed'])

    def test_large_static_attraction_does_not_hide_failed_longitudinal_force(self):
        first,second=pair()
        for row in second['steps']:row['material_source_force_n'][0]*=2
        value=mirror_checks(first,second)
        self.assertTrue(value['checks']['material_source_force_n']['passed'])
        self.assertFalse(value['checks']['material_source_force_n_longitudinal']['passed'])

    def test_changed_mesh_or_nonmirrored_poses_are_rejected(self):
        first,second=pair();second['mesh_sha256']='different'
        with self.assertRaises(ValueError):mirror_checks(first,second)
        first,second=pair();second['steps'][0]['source_offset_m']+=.001
        with self.assertRaises(ValueError):mirror_checks(first,second)
