import unittest
import numpy as np

from audit_imported_dc_zero_sections import probes
import test_prepare_imported_dc_source as imported


class ImportedZeroSectionSelectionTest(unittest.TestCase):
    def test_passive_trace_and_both_full_barrel_stubs_are_selected_before_field_errors(self):
        fixture=imported.ImportedPhysicalCopperTest().snapshot()
        fixture['networks'].append(dict(net='B',edges=[dict(geometry=dict(kind='trace',layer=1,points_m=[[0.,0.],[.01,0.]]))]))
        geometry=dict(translation_m=[0.,0.,0.],geometry=dict(full_physical_via_stubs=[dict(position_m=[.001,.002],
            full_centreplane_range_m=[-.0048,0.],electrical_landing_range_m=[-.0032,-.0016])]))
        selected=probes(fixture,geometry,{'A':{'current_a':1.}})
        self.assertEqual(len(selected),3)
        self.assertTrue(selected[0]['label'].startswith('passive:B:'))
        np.testing.assert_allclose([value['centre'][2] for value in selected[1:]],[-.004,-.0008])
        self.assertTrue(all(value['expected_area_m2']>0 for value in selected))
        fixture['networks'][-1]['edges']*=10
        self.assertEqual(len(probes(fixture,geometry,{'A':{'current_a':1.}})),8)
        self.assertEqual(len(probes(fixture,geometry,{'A':{'current_a':1.}},True)),12)
        root=np.sqrt(.5)
        fixture['networks'][-1]['edges'].append(dict(geometry=dict(kind='trace',layer=3,
            points_m=[[.001,0.],[.001*root,.001*root],[0.,.001]],
            circular_arc_m=dict(start=[.001,0.],mid=[.001*root,.001*root],end=[0.,.001]))))
        values=probes(fixture,geometry,{'A':{'current_a':1.}})
        arc=next(value for value in values if value['label'].startswith('passive-arc:'))
        np.testing.assert_allclose(arc['normal'],[-root,root,0.])
        self.assertEqual(len(values),9)
