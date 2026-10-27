import unittest

import numpy as np

from reduced_potential import MU0, constitutive, formulation, response_model, source_field
import test_project_static


class ReducedPotentialTest(unittest.TestCase):
    def test_reaction_tangent_matches_full_nonlinear_constitutive_residual(self):
        source=np.array([2000.,3000.,-1000.])
        for h in [np.array([200.,300.,-100.]),np.array([2000.,3000.,-1000.])]:
            gradient=source-h
            _,tangent=constitutive(h,130,.25)
            direction=np.array([.7,-.2,.4]);step=1e-3
            residual=lambda g:MU0*source-constitutive(source-g,130,.25)[0]
            difference=(residual(gradient+step*direction)-residual(gradient-step*direction))/(2*step)
            np.testing.assert_allclose(difference,tangent@direction,rtol=1e-8,atol=1e-12)
            self.assertGreater(np.linalg.eigvalsh(tangent).min(),0)

    def test_source_is_not_removed_when_pm_interfaces_are_removed_from_response_mesh(self):
        model=test_project_static.ProjectStaticTest().model();solver=response_model(model,True)
        self.assertEqual(solver['magnets'],[]);self.assertEqual(len(model['magnets']),5)
        text=formulation(model,solver)
        self.assertIn('Hsource[]',text);self.assertIn('mu0-mu[Hsource[]-{d phi}]',text)
        self.assertIn('IterativeLoop[100,1e-9,Relaxation]',text)
        self.assertNotIn('In Magnet',text)
        efficient=response_model(model,True,omit_inert=True)
        self.assertEqual(len(efficient['stack']),1)
        self.assertEqual(len(model['stack']),2)
        self.assertEqual(efficient['stack'][0]['origin_m'],solver['stack'][0]['origin_m'])
        b=source_field(model)(np.array([[0.,0.,.0008]]))
        self.assertGreater(np.linalg.norm(b),.1)
