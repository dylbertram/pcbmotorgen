import importlib.util
import unittest

import numpy as np

from finite_current_scalar import magnetization_h, scalar_form
from vector_material import MU0, h_b


@unittest.skipUnless(importlib.util.find_spec('ngsolve'), 'optional pinned magnetic environment')
class ScalarReactionTest(unittest.TestCase):
    def test_h_law_is_inverse_of_b_law_including_knee_and_zero(self):
        import ngsolve as ng
        from netgen.occ import Box, Pnt, OCCGeometry
        mesh = ng.Mesh(OCCGeometry(Box(Pnt(0, 0, 0), Pnt(1, 1, 1))).GenerateMesh(maxh=1.))
        point = mesh(.1, .2, .3)
        for mu, bsat in [(1., None), (130., None), (130., .25)]:
            for b in [(0., 0., 0.), (.01, -.02, .03), (.3, -.4, .2)]:
                vector = ng.CoefficientFunction(b)
                h = h_b(ng, vector, mu, bsat)
                recovered = MU0*(h+magnetization_h(ng, h, mu, bsat))
                np.testing.assert_allclose(recovered(point), b, atol=1e-14, rtol=1e-13)

    def test_linear_weak_form_has_positive_gauged_tangent_and_zero_source_limit(self):
        import ngsolve as ng
        from netgen.occ import Box, Pnt, OCCGeometry
        shape = Box(Pnt(0, 0, 0), Pnt(1, 1, 1))
        shape.mat('ferrite')
        shape.faces.name = 'outer'
        mesh = ng.Mesh(OCCGeometry(shape).GenerateMesh(maxh=.5))
        space = ng.H1(mesh, order=2, dirichlet='outer')
        model = {'stack': [{'name': 'ferrite', 'mu_r': 130., 'bsat_t': None}]}
        # Explicit air label is required by production material validation.
        from unittest.mock import patch
        with patch('finite_current_scalar.magnetic_regions', return_value=model['stack']):
            form = scalar_form(ng, space, mesh, model, ng.CoefficientFunction((0., 0., 0.)),
                               {ng.ET.TET: ng.IntegrationRule(ng.ET.TET, 6)})
        state = ng.GridFunction(space)
        residual = state.vec.CreateVector()
        form.Apply(state.vec, residual)
        self.assertEqual(residual.Norm(), 0.)
        free = np.asarray(space.FreeDofs(), dtype=bool)
        state.vec.FV().NumPy()[free] = np.random.default_rng(601).normal(size=int(free.sum()))
        self.assertGreater(form.Energy(state.vec), 0.)
