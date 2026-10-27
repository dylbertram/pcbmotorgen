import unittest

from audit_linear_dc_near_field import probes,validate_orders


class LinearNearFieldProbeTest(unittest.TestCase):
    def test_probe_selection_uses_actual_copper_depth_and_body_dimensions(self):
        sections=[dict(label=f'trace:A:{i}',centre_m=[i*.001,.002,.0008]) for i in range(5)]
        geometry=dict(translation_m=[0.,0.,.0012],geometry=dict(layers=[dict(centre_z_m=-.0004,thickness_m=35e-6)]))
        model=dict(stack=[dict(name='shield',origin_m=[-.01,-.005,-.0002],size_m=[.02,.01,.0002])],magnets=[])
        selected=probes(sections,geometry,model)
        self.assertEqual(len(selected),9)
        self.assertEqual(selected[0]['label'],'near:trace:A:0:2.5e-05')
        self.assertAlmostEqual(selected[0]['point_m'][2],.0008-17.5e-6-25e-6)
        self.assertEqual(selected[-2]['point_m'],[0.,0.,-.0001])
        self.assertTrue(all(p['role']=='near-copper-exterior' for p in selected[:6]))

    def test_no_field_error_or_archived_force_drives_selection(self):
        with self.assertRaisesRegex(ValueError,'inventory'):probes([],{},dict(stack=[],magnets=[]))

    def test_numerical_refinement_changes_order_not_points_or_gates(self):
        validate_orders([10,12])
        for orders in [[10],[12,10],[10,10],[10,14],[True,12]]:
            with self.assertRaisesRegex(ValueError,'increasing'):validate_orders(orders)
