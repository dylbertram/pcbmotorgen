import importlib.util
import unittest

import numpy as np

from finite_tetra_current_field import tetrahedron_field


def volume_quadrature(points, cell, current, count=24, slope=0.):
    """Independent tensor Gauss/Duffy volume integral, not the face formula."""
    nodes, weights = np.polynomial.legendre.leggauss(count)
    nodes, weights = (nodes+1)/2, weights/2
    u, v, w = np.meshgrid(nodes, nodes, nodes, indexing='ij')
    wu, wv, ww = np.meshgrid(weights, weights, weights, indexing='ij')
    coordinates = np.stack([u, (1-u)*v, (1-u)*(1-v)*w], axis=-1).reshape(-1, 3)
    matrix = cell[1:]-cell[0]
    sources = cell[0]+coordinates@matrix
    volumes = (wu*wv*ww*(1-u)**2*(1-v)*abs(np.linalg.det(matrix))).reshape(-1)
    result = []
    for point in points:
        displacement = point-sources
        kernel = displacement/np.linalg.norm(displacement, axis=1)[:, None]**3
        density=current+slope*(sources-cell.mean(axis=0))
        result.append(1e-7*np.cross(density, kernel).T@volumes)
    return np.array(result)


class FiniteTetraCurrentFieldTest(unittest.TestCase):
    def setUp(self):
        self.cell = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        self.points = np.array([[.2, .3, -.25], [1.7, -.4, .5], [-.4, .8, .9]])
        self.current = np.array([1.2, -.7, .4])

    def test_face_kernel_matches_independent_volume_quadrature(self):
        expected = volume_quadrature(self.points, self.cell, self.current)
        actual = tetrahedron_field(self.points, self.cell[None], self.current[None])
        np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-15)

    def test_near_face_is_not_replaced_by_softened_or_centreline_sources(self):
        points = np.array([[.2, .2, -.05]])
        first = volume_quadrature(points, self.cell, self.current, count=48)
        fine = volume_quadrature(points, self.cell, self.current, count=72)
        np.testing.assert_allclose(first, fine, rtol=2e-5, atol=1e-15)
        actual = tetrahedron_field(points, self.cell[None], self.current[None])
        np.testing.assert_allclose(actual, fine, rtol=2e-5, atol=1e-15)

    def test_orientation_translation_and_current_scaling_are_preserved(self):
        expected = tetrahedron_field(self.points, self.cell[None], self.current[None])
        reordered = self.cell[[0, 2, 1, 3]]
        shift = np.array([.2, -.7, .6])
        actual = tetrahedron_field(self.points+shift, (reordered+shift)[None], -2*self.current[None])
        np.testing.assert_allclose(actual, -2*expected, rtol=1e-12, atol=1e-20)

    def test_rt0_radial_term_is_not_silently_dropped(self):
        expected = volume_quadrature(self.points, self.cell, self.current, slope=.8)
        actual = tetrahedron_field(self.points, self.cell[None], self.current[None], radial_slope=np.array([.8]))
        np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-15)

    def test_thin_copper_scale_and_physical_clearance_keep_si_units(self):
        cell = self.cell*np.array([.001, .0002, .000035])
        points = np.array([[.0002, .00005, -.000035]])
        density = np.array([1e7, -2e6, 3e6])
        first = volume_quadrature(points, cell, density, count=96)
        fine = volume_quadrature(points, cell, density, count=144)
        np.testing.assert_allclose(first, fine, rtol=2e-5, atol=1e-12)
        actual = tetrahedron_field(points, cell[None], density[None])
        np.testing.assert_allclose(actual, fine, rtol=2e-5, atol=1e-12)

    @unittest.skipUnless(importlib.util.find_spec('ngsolve'), 'optional pinned volume quadrature required')
    def test_streamed_reference_integrator_uses_the_physical_affine_cell(self):
        import ngsolve as ng
        from audit_finite_current_source_field import volume_field
        expected = volume_quadrature(self.points, self.cell, self.current, slope=.8)
        actual = volume_field(self.points, self.cell[None], self.current[None], np.array([.8]), ng.IntegrationRule(ng.ET.TET, 24))
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=1e-14)

    def test_cell_and_observation_batching_do_not_change_superposition(self):
        other = self.cell+np.array([2., 0., 0.])
        cells = np.stack([self.cell, other])
        currents = np.stack([self.current, -.3*self.current])
        full = tetrahedron_field(self.points, cells, currents)
        bounded = tetrahedron_field(self.points, cells, currents, batch_cells=1, batch_points=1)
        np.testing.assert_allclose(bounded, full, rtol=1e-13, atol=1e-20)

    def test_interior_boundary_and_degenerate_cells_are_rejected(self):
        for point in [[.1, .1, .1], [.2, .2, 0.]]:
            with self.assertRaises(ValueError):
                tetrahedron_field(np.array([point]), self.cell[None], self.current[None])
        degenerate = self.cell.copy()
        degenerate[3] = degenerate[2]
        with self.assertRaises(ValueError):
            tetrahedron_field(self.points, degenerate[None], self.current[None])


if __name__ == '__main__':
    unittest.main()
