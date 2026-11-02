import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_compact_star_scaling import compare_pairs, graph
from audit_compact_spread_dxf import raw_edges


class CompactScalingAuditTest(unittest.TestCase):
    def test_multilayer_raw_reader_keeps_physical_z_and_requires_explicit_layer_count(self):
        pairs = [(0, 'SECTION'), (2, 'ENTITIES')]
        for depth in range(4):
            z = -1.6 * depth
            pairs.extend([(0, 'LINE'), (8, 'L_A'), (10, 0), (20, 0), (30, z),
                          (11, 1), (21, 1), (31, z)])
        pairs.extend([(0, 'ENDSEC'), (0, 'EOF')])
        with TemporaryDirectory() as folder:
            path = Path(folder)/'four.dxf'
            path.write_text(''.join(f'{code}\n{value}\n' for code, value in pairs))
            with self.assertRaises(AssertionError):
                raw_edges(path)
            edges, counts = raw_edges(path, expected_layers=4)
            self.assertEqual(counts, {'LINE': 4})
            self.assertEqual([a[2] for _, a, _ in edges], [-1.6*i for i in range(4)])

    def test_driver_is_a_physical_lead_not_the_leftmost_body_node(self):
        # A's body also reaches X=0. Picking the minimum-X node would create
        # a fictitious excitation inside the braid and corrupt current signs.
        driver, body, turn, neutral = (0, 9, 0), (0, 4, 0), (4, 4, 0), (4, 4, -1.6)
        edges = [('A', a, b) for a, b in [(driver, body), (body, turn), (turn, neutral)]]
        receipt, current = graph(edges, 'A', (4000, 4000, -1600))
        self.assertTrue(receipt['connected'])
        self.assertEqual(receipt['driver_xyz_mm'], [0, 9, 0])
        self.assertAlmostEqual(next(iter(current.values())), 1)

    def test_disconnected_copper_is_recorded_without_bridging_it(self):
        edges = [('B', (0, 9, 0), (1, 9, 0)), ('B', (1.01, 9, 0), (2, 9, 0))]
        receipt, current = graph(edges, 'B', (2000, 9000, 0))
        self.assertFalse(receipt['connected'])
        self.assertEqual(len(receipt['degree_one_xyz_mm']), 4)
        self.assertEqual(current, {})

    def test_pair_comparison_keeps_current_sign_and_missing_phases(self):
        xy = ((0, 0), (1000, 1000))
        reference = {p: {(0, xy): 1} for p in 'ABC'}
        currents = {'A': {(0, xy): 1, (2, xy): -1}, 'B': {}, 'C': {(0, xy): 1, (2, xy): 1}}
        result = compare_pairs(currents, reference, 2)
        self.assertEqual(result['A'][1]['directed_current_cosine'], -1)
        self.assertEqual(result['A'][1]['same_direction_fraction'], 0)
        self.assertEqual(result['C'][1]['same_direction_fraction'], 1)
        self.assertFalse(result['B'][0]['connected'])


if __name__ == '__main__':
    unittest.main()
