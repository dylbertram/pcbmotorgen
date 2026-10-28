import unittest

from export_bias_winding import geometry_copy


class BiasWindingExportTest(unittest.TestCase):
    def test_only_archived_copy_loses_material_not_geometry_or_drive(self):
        original={'versions':[{'state':{'config':{'pcb_thickness_mm':.8,'trace_width_mm':.2,
            'drive':{'outer_copper_oz':3},'backplane':{'layers':[{'thickness_m':.0002}]}},
            'cad_geometry':{'layer_z_mm':[-.8,0.]},'mover_position_mm':41.4}}]}
        derived,material=geometry_copy(original,0)
        self.assertIsNone(derived['versions'][0]['state']['config']['backplane'])
        self.assertEqual(original['versions'][0]['state']['config']['backplane'],material)
        derived['versions'][0]['state']['config']['backplane']=material
        self.assertEqual(derived,original)
