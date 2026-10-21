import unittest

from finite_copper_eligibility import require_network_representable
from finite_copper_geometry import dimensions
import test_prepare_imported_dc_source as imported


class LegacyCopperEligibilityTest(unittest.TestCase):
    def test_through_barrel_stubs_cannot_be_silently_dropped(self):
        snapshot=imported.ImportedPhysicalCopperTest().snapshot()
        with self.assertRaisesRegex(ValueError,'truncate'):
            require_network_representable(snapshot,dimensions(snapshot))

    def test_gapped_barrels_cannot_be_silently_joined(self):
        snapshot=imported.ImportedPhysicalCopperTest().snapshot()
        snapshot['routing']['vias']=[dict(position=dict(x=1.,y=2.),from_layer=0,to_layer=1,net='A'),
                                    dict(position=dict(x=1.,y=2.),from_layer=2,to_layer=3,net='A')]
        snapshot['networks'][0]['edges']=[dict(geometry=dict(kind='via',position_m=[.001,.002],layers=[0,1])),
                                        dict(geometry=dict(kind='via',position_m=[.001,.002],layers=[2,3]))]
        with self.assertRaisesRegex(ValueError,'fill a gap'):
            require_network_representable(snapshot,dimensions(snapshot))

    def test_complete_contiguous_physical_barrel_is_allowed(self):
        snapshot=imported.ImportedPhysicalCopperTest().snapshot()
        snapshot['networks'][0]['edges']=[dict(geometry=dict(kind='via',position_m=[.001,.002],layers=[0,1])),
            dict(geometry=dict(kind='via',position_m=[.001,.002],layers=[1,2])),
            dict(geometry=dict(kind='via',position_m=[.001,.002],layers=[2,3]))]
        require_network_representable(snapshot,dimensions(snapshot))

    def test_raw_circle_is_not_replaced_by_a_polyline(self):
        snapshot=imported.ImportedPhysicalCopperTest().snapshot();snapshot['routing']['curves']=[{'actual':'circle'}]
        with self.assertRaisesRegex(ValueError,'no chord substitution'):
            require_network_representable(snapshot,dimensions(snapshot))
