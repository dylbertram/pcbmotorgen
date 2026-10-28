import unittest

import test_prepare_imported_dc_source as imported
from prepare_imported_dc_source import build
from audit_imported_dc_cad import checks


class ImportedCadAuditTest(unittest.TestCase):
    def test_full_stub_and_bore_queries_pass_exact_saved_via(self):
        snapshot=imported.ImportedPhysicalCopperTest().snapshot();shape,geometry=build(snapshot)
        result=checks(shape,snapshot,geometry)
        self.assertTrue(result['passed']);self.assertEqual(len(result['stub_sections']),2)
        self.assertEqual(result['bore_copper_volume_m3'],0.)

    def test_added_gap_copper_is_detected_without_truncation_or_priority(self):
        snapshot=imported.ImportedPhysicalCopperTest().snapshot()
        snapshot['routing']['vias']=[dict(position=dict(x=1.,y=2.),from_layer=0,to_layer=1,net='A'),
            dict(position=dict(x=1.,y=2.),from_layer=2,to_layer=3,net='A')]
        shape,geometry=build(snapshot)
        self.assertTrue(checks(shape,snapshot,geometry)['passed'])
        from netgen.occ import Cylinder,Pnt,Dir
        changed=shape+Cylinder(Pnt(.001,.002,-.0025),Dir(0,0,1),.0001,.0002)
        result=checks(changed,snapshot,geometry)
        self.assertGreater(result['gap_copper_volume_m3'],0.)
        self.assertFalse(result['passed'])
