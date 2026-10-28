import tempfile
import unittest
from pathlib import Path

from check_finite_plate import elmer_input, validate_mesh, require_elmer_nonlinear_convergence


class FiniteInputTest(unittest.TestCase):
    def test_nonlinear_convergence_ignores_field_projection_norms(self):
        log='''ComputeChange: NS (ITER=16) (NRM,RELC): ( 0.12014994E-06 0.89909733E-08 ) :: mgdynamics
ComputeChange: NS (ITER=3) (NRM,RELC): ( 0.23420517 0.95676592 ) :: mgdynamicscalc
'''
        self.assertEqual(require_elmer_nonlinear_convergence(log)['iterations'],16)
        with self.assertRaises(ValueError):
            require_elmer_nonlinear_convergence(log.splitlines()[1])
        with self.assertRaises(ValueError):
            require_elmer_nonlinear_convergence(log.replace('0.89909733E-08','0.89909733E-02'))

    def test_linear_and_nonlinear_use_same_named_boundary_and_pm(self):
        for mode in range(3):
            text = elmer_input(mode, 130, 0.25)
            self.assertEqual(text.count('Body 3\n'), 1)
            self.assertIn('Target Boundaries(1) = $ outer', text)
            self.assertIn('Magnetization 3 = Real 1066338.1187162634', text)
            self.assertIn('Linear System Abort Not Converged = True', text)
            self.assertEqual('INCLUDE HB' in text, mode == 2)
            self.assertIn('Relative Permeability = '+str(1 if mode == 0 else 130), text)

    def test_missing_materials_cannot_pass_mesh_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.msh'
            path.write_text('''$Nodes
4
1 0 0 0
2 1 0 0
3 0 1 0
4 0 0 1
$EndNodes
$Elements
1
1 4 2 1 1 1 2 3 4
$EndElements
''')
            with self.assertRaises(AssertionError):
                validate_mesh(path,0.005,0.03)


if __name__ == '__main__':
    unittest.main()
