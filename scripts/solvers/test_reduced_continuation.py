import tempfile
import unittest
from pathlib import Path

import numpy as np

from reduced_continuation import solution_values, with_initial


class ReducedContinuationTest(unittest.TestCase):
    def test_real_coefficients_and_initialization_are_not_reinterpreted(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.res'
            text='$ResFormat\n1.1 0\n$EndResFormat\n$Solution\n0 0 0 0\n1.2 0\n-4.5 0\n$EndSolution\n'
            path.write_text(text);np.testing.assert_array_equal(solution_values(path),[1.2,-4.5])
            path.write_text(text.replace('1.2 0','1.2 1'))
            with self.assertRaises(ValueError):solution_values(path)
        changed=with_initial('InitSolution[S]; GenerateJac[S];')
        self.assertIn('CopySolution[InitialValues(),S]',changed)
        self.assertIn('initial-reaction.pos',changed)
        with self.assertRaises(ValueError):with_initial('unknown initializer')
