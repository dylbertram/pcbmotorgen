import unittest
import tempfile
from pathlib import Path

import numpy as np

from spectral_transient import Transient,run
from spectral_biased_ac import bias_state


class NonlinearTimeTest(unittest.TestCase):
    def test_harmonic_seed_retains_nonlinear_gates_and_immutable_absolute_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            trace=Path(directory)/'trace.npz'
            result=run(.0002,130.,1000.,frequency=1000.,fraction=1e-3,cells=4,modes=1,samples=32,
                steps_per_period=32,periods=4,wall_cells=8,gap_cells=2,layer_conductivity=.2,
                harmonic_initial_guess=True,trace_path=trace)
            self.assertLess(result['periodic_settlement_relative_change'],1e-9)
            self.assertLess(result['max_step_relative_residual'],1e-10)
            self.assertEqual(result['initial_guess'],'discrete-harmonic-tangent-orbit')
            with np.load(trace) as raw:
                self.assertEqual(raw['midpoints'].shape[0],64)
                np.testing.assert_allclose(2*raw['midpoints'],raw['previous']+raw['next'],rtol=1e-12,atol=1e-15)
            with self.assertRaisesRegex(ValueError,'Preserve previous'):
                run(.0002,130.,1000.,trace_path=trace)

    def test_linear_limit_time_refines_toward_complex_skin_response(self):
        results=[run(0.0002,130,1000,frequency=1000,fraction=1e-3,cells=4,modes=1,samples=32,
                     steps_per_period=n,periods=5,wall_cells=8,gap_cells=2) for n in [32,64]]
        self.assertLess(results[1]['absolute_reflection_difference'],results[0]['absolute_reflection_difference'])
        self.assertLess(results[1]['absolute_reflection_difference'],0.003)
        self.assertLess(results[1]['relative_power_balance_error'],1e-6)
        self.assertEqual(results[1]['quadrature_fraction_crossing_knee'],0)
        self.assertLess(results[1]['top_a_harmonics_2_to_5_relative'],1e-6)
        self.assertGreater(results[1]['incident_ripple_peak_b_t'],0)

    def test_tail_matrices_are_symmetric_and_conductivity_is_passive(self):
        plate,_,_=bias_state(0.0002,130,0.25,4,1,32)
        transient=Transient(plate,wall_cells=8)
        np.testing.assert_allclose(transient.stiffness.toarray(),transient.stiffness.toarray().T,atol=1e-9)
        eigenvalues=np.linalg.eigvalsh(transient.mass.toarray())
        self.assertGreaterEqual(eigenvalues.min(),-1e-12)
        self.assertGreater(eigenvalues.max(),0)
        with self.assertRaises(ValueError):Transient(plate,conductivity=-1)


if __name__=='__main__':unittest.main()
