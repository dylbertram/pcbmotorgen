import copy
import unittest

from audit_periodic_nonlinear_controls import control_axis


class NonlinearPeriodicControlsTest(unittest.TestCase):
    def test_time_and_space_cannot_be_refined_together(self):
        a={'backend':'FE','physical':[.002,2500.,.45,.2,1e5],'fraction':.001,'phase':0,
            'resolution':{'steps_per_period':64,'nx':48,'cells':12,'far':.02,'air_cells':20}}
        b=copy.deepcopy(a);b['resolution']['steps_per_period']=128;control_axis(a,b,'time')
        b['resolution']['nx']=96
        with self.assertRaisesRegex(ValueError,'changed together'):control_axis(a,b,'time')
        b=copy.deepcopy(a);b['phase']=1;b['resolution']['steps_per_period']=128
        with self.assertRaisesRegex(ValueError,'Different nonlinear'):control_axis(a,b,'time')

    def test_outer_air_expansion_keeps_physical_spacing(self):
        a={'backend':'FE','physical':[],'fraction':.001,'phase':0,'resolution':{'far':.02,'air_cells':20}}
        b=copy.deepcopy(a);b['resolution'].update(far=.03,air_cells=30);control_axis(a,b,'domain')
        b['resolution']['air_cells']=20
        with self.assertRaisesRegex(ValueError,'physical air spacing'):control_axis(a,b,'domain')
