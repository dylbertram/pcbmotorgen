import copy
import unittest

from audit_housing_motion_controls import control_axis,changes


class MotionControlsTest(unittest.TestCase):
    def setUp(self):
        self.base={'model':{'test':1},'housing':{'test':1},'source_summary_sha256':'source','version':'pinned',
            'mesh_sha256':'mesh','request':{'steps':24,'mesh':.002,'far':.04,'bonus_order':4,'speed':20.,'save_every':12},
            'joule_energy_j':1.,'source_work_energy_j':1.1,'reaction_energy_end_j':.1,
            'steps':[{'source_offset_m':x,'housing_source_interaction_force_n':[.8,0.,-.2]} for x in [-.5,.5]]}

    def test_time_control_requires_identical_mesh_and_no_other_axis_change(self):
        fine=copy.deepcopy(self.base);fine['request']['steps']=48
        control_axis(self.base,fine,'time')
        fine['mesh_sha256']='different'
        with self.assertRaises(ValueError):control_axis(self.base,fine,'time')
        fine['mesh_sha256']='mesh';fine['request']['mesh']=.0015
        with self.assertRaises(ValueError):control_axis(self.base,fine,'time')

    def test_small_loss_change_does_not_hide_unconverged_stored_energy(self):
        fine=copy.deepcopy(self.base);fine['reaction_energy_end_j']=.095
        self.assertFalse(changes(self.base,fine)['passed'])
        fine['reaction_energy_end_j']=.099
        self.assertTrue(changes(self.base,fine)['passed'])
