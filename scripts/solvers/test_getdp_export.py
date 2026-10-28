import unittest

from audit_getdp_export import compare


class GetdpExportTest(unittest.TestCase):
    def test_affine_export_gate_rejects_errors_and_nonfinite_values(self):
        self.assertTrue(compare([[1.,2.,3.]],[[1.,2.,3.]])['passed'])
        self.assertFalse(compare([[1.,2.,3.01]],[[1.,2.,3.]])['passed'])
        for actual,expected in [([[float('nan'),0,0]],[[1,0,0]]),([[1,0]],[[1,0,0]])]:
            with self.assertRaises(ValueError):compare(actual,expected)
