import importlib.util
import unittest

from audit_copper_magnetic_overlap import add_clipped, layer_intervals, overlap_depth, rectangular_bounds


class CopperMagneticOverlapTest(unittest.TestCase):
    def test_saved_centreplanes_are_translated_without_reinterpreting_surfaces(self):
        spec = {'layers': [
            {'layer': 0, 'centre_z_m': 0., 'thickness_m': 35e-6},
            {'layer': 1, 'centre_z_m': -.0008, 'thickness_m': 35e-6},
        ]}
        layers = layer_intervals(spec, [-.0534, -.004, .0008])
        self.assertAlmostEqual(layers[0]['centre_z_m'], .0008)
        self.assertAlmostEqual(layers[1]['low_z_m'], -17.5e-6)
        self.assertAlmostEqual(layers[1]['high_z_m'], 17.5e-6)
        self.assertAlmostEqual(overlap_depth((layers[1]['low_z_m'], layers[1]['high_z_m']), (-.0002, 0.)), 17.5e-6)

    def test_contact_has_zero_depth_and_a_real_gap_is_not_invented(self):
        self.assertEqual(overlap_depth((0., 35e-6), (-.0002, 0.)), 0.)
        self.assertEqual(overlap_depth((10e-6, 45e-6), (-.0002, 0.)), 0.)

    def test_invalid_dimensions_and_intervals_are_rejected(self):
        for shift in [[0., 0.], [0., 0., float('nan')]]:
            with self.assertRaises(ValueError):
                layer_intervals({'layers': []}, shift)
        with self.assertRaises(ValueError):
            layer_intervals({'layers': [{'layer': 0, 'centre_z_m': 0., 'thickness_m': -1.}]}, [0., 0., 0.])
        with self.assertRaises(ValueError):
            overlap_depth((1., 0.), (0., 1.))
        with self.assertRaises(ValueError):
            rectangular_bounds({'origin_m': [0., 0., 0.], 'size_m': [1., 0., 1.]})

    def test_nominal_ferrite_envelope_is_preserved(self):
        low, high = rectangular_bounds({'origin_m': [-.018, -.006, -.0002], 'size_m': [.036, .012, .0002]})
        self.assertEqual(low[2], -.0002)
        self.assertAlmostEqual(high[2], 0.)

    @unittest.skipUnless(importlib.util.find_spec('matplotlib'), 'optional picture environment required')
    def test_physical_footprint_clip_survives_axes_insertion(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, Rectangle
        import numpy as np
        fig, axes = plt.subplots()
        clip = Rectangle((1, 2), 3, 4)
        axes.add_patch(clip)
        patch = Circle((0, 0), 10)
        add_clipped(axes, patch, clip)
        np.testing.assert_allclose(patch.get_clip_box().extents, clip.get_window_extent().extents)
        plt.close(fig)


if __name__ == '__main__':
    unittest.main()
