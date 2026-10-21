import unittest

import test_project_static
from reduced_potential import formulation, response_model
from reduced_residual_trial import explicit_formulation


class ReducedResidualTrialTest(unittest.TestCase):
    def test_full_residual_keeps_material_law_and_analytic_source(self):
        model=test_project_static.ProjectStaticTest().model();solver=response_model(model,True)
        original=formulation(model,solver);changed=explicit_formulation(original,solver)
        self.assertIn('mu0*Hsource[]-mu[Hsource[]-$1]*(Hsource[]-$1)',changed)
        self.assertIn('JacNL [FullTangent[{d phi}]*Dof{d phi}',changed)
        self.assertIn('FluxResidual[Region[8]]=mu0*$1;',changed)
        self.assertIn('IterativeLoop[100,1e-9,Relaxation]',changed)
        self.assertEqual(changed.count('Hsource[]=Bsource[]/mu0;'),1)
        with self.assertRaises(ValueError):explicit_formulation('unrecognized',solver)
