import unittest

import numpy as np

from periodic_motion import moving_source,run
from spectral_biased_ac import bias_state
from spectral_plate import MU0


class PeriodicMotionTest(unittest.TestCase):
    def test_linear_motion_recovers_continuous_depth_loss_and_reverse_symmetry(self):
        results=[run(v,bsat=1000,cells=4,modes=1,samples=32,steps_per_period=256,
                     periods=8,wall_cells=8,gap_cells=2) for v in [20,-20]]
        a,b=results
        self.assertLess(abs(a['joule_w_m2']/a['linear_continuous_depth_loss_w_m2']-1),0.005)
        self.assertAlmostEqual(a['joule_w_m2']/b['joule_w_m2'],1,places=8)
        self.assertAlmostEqual(a['magnet_force_density_n_m2']/b['magnet_force_density_n_m2'],-1,places=8)
        self.assertLess(a['relative_source_joule_error'],0.02)
        self.assertLess(a['relative_drag_joule_error'],0.02)

    def test_mechanical_source_derivative_is_not_a_power_inferred_force(self):
        plate,_,_=bias_state(0.0002,130,0.25,4,3,128)
        source,derivative=moving_source(plate,0.0003);h=1e-8
        numerical=(moving_source(plate,0.0003+h)[0]-moving_source(plate,0.0003-h)[0])/(2*h)
        np.testing.assert_allclose(numerical,derivative,rtol=1e-8,atol=1e-3)
        np.testing.assert_allclose(moving_source(plate,0)[0],plate.incident/MU0)
        self.assertAlmostEqual(float(source@source),float((plate.incident/MU0)@(plate.incident/MU0)),places=4)

    def test_zero_velocity_rejects_no_physics_and_produces_no_eddy_force(self):
        result=run(0,cells=4,modes=1,samples=32,wall_cells=8)
        self.assertEqual(result['joule_w_m2'],0)
        self.assertEqual(result['magnet_force_density_n_m2'],0)
        with self.assertRaises(ValueError):run(float('nan'))


if __name__=='__main__':unittest.main()
