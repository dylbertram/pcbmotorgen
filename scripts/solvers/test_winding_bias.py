import unittest

import numpy as np

from audit_winding_bias import lorentz_coefficient,reference_for


class WindingBiasTest(unittest.TestCase):
    def test_mesh_refinement_never_inherits_the_looser_backend_gate(self):
        backends=['GetDP','NGSolve','NGSolve']
        self.assertEqual(reference_for(backends,1),(0,.05))
        self.assertEqual(reference_for(backends,2),(1,.02))

    def test_force_on_copper_has_the_correct_cross_product_and_current_sign(self):
        dl=np.array([[0.,.01,0.],[0.,0.,-.002]])
        field=np.array([[0.,0.,.5],[.3,0.,0.]])
        np.testing.assert_allclose(lorentz_coefficient(dl,field),[.005,-.0006,0.])
        np.testing.assert_allclose(lorentz_coefficient(-dl,field),[-.005,.0006,0.])

    def test_uniform_field_force_on_closed_current_path_is_zero(self):
        dl=np.array([[1.,0.,0.],[0.,1.,0.],[-1.,0.,0.],[0.,-1.,0.]])
        np.testing.assert_allclose(lorentz_coefficient(dl,np.tile([.2,.3,.4],(4,1))),0.,atol=1e-15)
