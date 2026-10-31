import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from audit_braid_layer_force import audit, harmonic


class LayerForceAuditTest(unittest.TestCase):
    def test_opposing_layers_cancel_instead_of_summing_absolute_force(self):
        x = np.linspace(.0145, .0505, 49)
        wave = np.sin(2 * np.pi * x / .012 + .7)
        first = harmonic(x, .03 * wave, .012)
        second = harmonic(x, -.02 * wave, .012)
        combined = harmonic(x, .03 * wave - .02 * wave, .012)
        self.assertAlmostEqual(combined['amplitude_n_per_a'], .01, places=12)
        self.assertAlmostEqual(combined['sine_offset_deg'], np.degrees(.7), places=10)
        self.assertAlmostEqual(abs(first['sine_offset_deg'] - second['sine_offset_deg']), 180, places=10)
        self.assertAlmostEqual(combined['amplitude_n_per_a'] / (first['amplitude_n_per_a'] + second['amplitude_n_per_a']), .2, places=12)

    def test_refuses_mixed_conductor_meshes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, native = root / 'fixture.json', root / 'native.json'
            fixture.write_text(json.dumps({'force_subdivisions': 20}))
            native.write_text(json.dumps({'meshing': 40}))
            with self.assertRaisesRegex(ValueError, 'meshes differ'):
                audit(fixture, native)


if __name__ == '__main__':
    unittest.main()
