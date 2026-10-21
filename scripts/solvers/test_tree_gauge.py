import unittest

from tree_gauge import tree_edges


class TreeGaugeTest(unittest.TestCase):
    def test_outer_vertices_are_one_root_without_artificial_internal_buses(self):
        selected=tree_edges(range(5),[(0,0,1),(1,1,2),(2,2,3),(3,3,4),(4,4,0),(5,1,4)],{0,1})
        self.assertEqual(len(selected),3)
        self.assertNotIn(0,selected)

    def test_missing_root_or_disconnected_mesh_is_rejected(self):
        with self.assertRaises(ValueError):tree_edges(range(3),[(0,0,1)],{0})
        with self.assertRaises(ValueError):tree_edges(range(2),[(0,0,1)],set())
