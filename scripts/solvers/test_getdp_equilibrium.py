import tempfile
import unittest
from pathlib import Path

from getdp_equilibrium_check import certificate, certified_formulation


class GetDPEquilibriumTest(unittest.TestCase):
    def test_actual_equation_residual_not_the_update_proxy_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);path=work/'equilibrium.txt'
            path.write_text('1e-10 2 0.001 1e-13\n')
            self.assertEqual(certificate(work)['relative_residual'],1e-10)
            for row in ['0 2 0.001 0.0001','1e-5 2 0.001 1e-8','nan 2 0.001 0','0 2 0 0']:
                path.write_text(row+'\n')
                with self.assertRaises(ValueError):certificate(work)
        text=certified_formulation('FluxResidual[]\nResolution {old}\nPostProcessing {old}\n')
        self.assertIn('GetResidual[S,$CertResidual]',text)
        self.assertIn('$CertRelative>1e-9',text)
        self.assertNotIn('IterativeLoop[',text)
