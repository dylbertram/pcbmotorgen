import unittest

import numpy as np

from finite_current_tree import FiniteCurrentTree
from finite_tetra_current_field import tetrahedron_field


class FiniteCurrentTreeTest(unittest.TestCase):
    def setUp(self):
        cell = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.], [0., 0., .1]])
        self.cells = np.stack([cell+np.array([x, y, 0.]) for x in [-.4, 0., .4] for y in [-.3, .3]])
        self.mean = np.random.default_rng(801).normal(size=(len(self.cells), 3))
        self.slope = np.linspace(-.7, .8, len(self.cells))
        self.points = np.array([[.1, .2, -.03], [1.2, -.6, .5], [5., -3., 7.]])

    def test_zero_opening_is_exact_finite_source_not_a_filament(self):
        tree = FiniteCurrentTree(self.cells, self.mean, self.slope, leaf_size=2)
        expected = tetrahedron_field(self.points, self.cells, self.mean, radial_slope=self.slope)
        np.testing.assert_allclose(tree.field(self.points, opening=0.), expected, rtol=1e-11, atol=1e-20)
        self.assertEqual(tree.last_evaluation['far_point_nodes'], 0)
        self.assertEqual(tree.last_evaluation['exact_point_cell_pairs'], len(self.points)*len(self.cells))

    def test_second_order_finite_moments_match_direct_far_field(self):
        tree = FiniteCurrentTree(self.cells, self.mean, self.slope, leaf_size=1)
        points = np.array([[10., -6., 14.], [-9., 8., 11.]])
        expected = tetrahedron_field(points, self.cells, self.mean, radial_slope=self.slope)
        actual = tree.field(points, opening=.3)
        self.assertGreater(tree.last_evaluation['far_point_nodes'], 0)
        np.testing.assert_allclose(actual, expected, rtol=.002, atol=1e-18)

    def test_moment_translation_is_independent_of_tree_partition(self):
        first = FiniteCurrentTree(self.cells, self.mean, self.slope, leaf_size=1)
        second = FiniteCurrentTree(self.cells, self.mean, self.slope, leaf_size=len(self.cells))
        for name in ['w', 'q', 't']:
            np.testing.assert_allclose(getattr(first.nodes[0], name), getattr(second.nodes[0], name), rtol=1e-12, atol=1e-20)

    def test_interior_and_invalid_controls_are_not_softened(self):
        tree = FiniteCurrentTree(self.cells, self.mean, self.slope)
        with self.assertRaises(ValueError):
            tree.field(self.cells[0].mean(axis=0)[None])
        for opening in [-1., 1., float('nan')]:
            with self.assertRaises(ValueError):
                tree.field(self.points, opening)


if __name__ == '__main__':
    unittest.main()
