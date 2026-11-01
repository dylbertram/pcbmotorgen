import unittest

from audit_compact_spread_dxf import planar_contacts, balanced_force


class ActualDxfAuditTest(unittest.TestCase):
    def test_rejects_junction_hidden_inside_a_trace(self):
        edges=[('A',(0,0,0),(2,0,0)),('A',(1,0,0),(1,1,0))]
        with self.assertRaisesRegex(AssertionError,'misses real planar junctions'):
            planar_contacts(edges)

    def test_other_layer_crossing_is_not_a_junction(self):
        edges=[('A',(0,0,0),(2,0,0)),('B',(1,-1,-1.6),(1,1,-1.6))]
        self.assertEqual(planar_contacts(edges)['cross_phase_centerline_contacts'],[])

    def test_reports_actual_star_neutral(self):
        edges=[('A',(0,0,-1.6),(1,0,-1.6)),('B',(1,0,-1.6),(1,1,-1.6))]
        result=planar_contacts(edges)
        self.assertEqual(result['unmodeled_planar_junctions'],[])
        self.assertEqual(result['cross_phase_centerline_contacts'][0]['xyz_mm'],[1,0,-1.6])

    def test_rejects_overlapping_centerlines(self):
        with self.assertRaisesRegex(AssertionError,'Overlapping actual copper'):
            planar_contacts([('A',(0,0,0),(2,0,0)),('B',(1,0,0),(3,0,0))])

    def test_balanced_drive_sums_phase_force_with_signed_currents(self):
        result=balanced_force([0.0],[[1.0,0.0,0.0]],1.0,1.5707963267948966)
        self.assertAlmostEqual(result['mean_n'],1.0)


if __name__ == '__main__':
    unittest.main()
