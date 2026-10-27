import importlib.util
import unittest

import numpy as np

from finite_current_quadrature import check_rules, material_layout, source_components, weighted_rule_values


@unittest.skipUnless(importlib.util.find_spec('ngsolve'), 'optional pinned quadrature storage environment')
class FiniteCurrentQuadratureTest(unittest.TestCase):
    def test_exact_rule_physical_values_are_stored_without_projection(self):
        import ngsolve as ng
        from netgen.occ import Box, Pnt, OCCGeometry
        shape = Box(Pnt(0, 0, 0), Pnt(1, 1, 1))
        shape.mat('material')
        mesh = ng.Mesh(OCCGeometry(shape).GenerateMesh(maxh=.6))
        layout = material_layout(ng, mesh, 'material', 4)
        points = layout.points
        values = np.column_stack([points[:, 0]+2*points[:, 1], points[:, 2], -points[:, 0]])
        coefficient, components, metadata = source_components(ng, mesh, layout, values)
        self.assertEqual(len(components), 3)
        self.assertEqual(coefficient.dim, 3)
        self.assertLessEqual(metadata['maximum_relative_storage_error'], 1e-13)
        recovered_points, weighted = weighted_rule_values(ng, mesh, layout, coefficient, 'material')
        np.testing.assert_array_equal(recovered_points, points)
        np.testing.assert_allclose(weighted.sum(axis=0), [1.5, .5, -.5], rtol=1e-13)
        with self.assertRaises(ValueError):
            check_rules(ng, layout, 6)
        with self.assertRaises(ValueError):
            source_components(ng, mesh, layout, values[:-1])

    def test_degree_eight_curved_air_and_thin_material_use_native_rule_evaluation(self):
        import ngsolve as ng
        from netgen.occ import Box, Sphere, Pnt, OCCGeometry, Glue
        body = Box(Pnt(-.4, -.3, -.0025), Pnt(.4, .3, -.0005))
        body.mat('material')
        air = Sphere(Pnt(0, 0, 0), 1.)-body
        air.mat('air')
        mesh = ng.Mesh(OCCGeometry(Glue([air, body])).GenerateMesh(maxh=.3))
        mesh.Curve(2)
        layout = material_layout(ng, mesh, 'material', 8)
        values = np.random.default_rng(906).normal(size=layout.points.shape)
        coefficient, _, metadata = source_components(ng, mesh, layout, values)
        norm = ng.Integrate(ng.InnerProduct(coefficient, coefficient)*ng.dx(
            definedon=mesh.Materials('material'), intrules=layout.rules), mesh)
        self.assertGreater(norm, 0.)
        self.assertLess(metadata['maximum_relative_storage_error'], 1e-13)


if __name__ == '__main__':
    unittest.main()
