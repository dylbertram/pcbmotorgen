import math
import unittest

import numpy as np

from finite_circular_copper import parameters, solid, chord_control, section_plane


class CircularCopperTest(unittest.TestCase):
    def primitive(self, sweep=math.pi/2, shift=(.01, -.004)):
        return {key:(np.asarray(shift)+.001*np.array([math.cos(angle), math.sin(angle)])).tolist()
                for key, angle in zip(['start', 'mid', 'end'], [0., sweep/2, sweep])}

    def test_minor_major_and_reversed_arcs_preserve_circle_length(self):
        for sweep in [math.pi/2, -math.pi/2, 3*math.pi/2, -3*math.pi/2]:
            spec = parameters(self.primitive(sweep))
            self.assertAlmostEqual(spec['radius_m'], .001, places=14)
            self.assertAlmostEqual(spec['sweep_rad'], sweep, places=12)
            self.assertAlmostEqual(spec['length_m'], .001*abs(sweep), places=14)
            plane=section_plane(self.primitive(sweep),-.0048,.0002)
            mid_angle=sweep/2
            np.testing.assert_allclose(plane['normal'],np.sign(sweep)*np.array([-math.sin(mid_angle),math.cos(mid_angle),0.]),atol=1e-12)
            self.assertEqual(plane['centre'][2],-.0048)

    def test_exact_occ_volume_depth_and_end_caps(self):
        for sweep in [math.pi/2, -3*math.pi/2]:
            width, thickness, z = .0002, 35e-6, -.0048
            shape = solid(self.primitive(sweep), z, width, thickness)
            # Ring-sector area is R*width*angle. The two exterior semicircular
            # end caps together contribute one disk, without polygonal joints.
            expected = (.001*width*abs(sweep)+math.pi*(width/2)**2)*thickness
            self.assertAlmostEqual(shape.mass/expected, 1., places=9)
            self.assertEqual(len(shape.solids), 1)
            from netgen.occ import Box, Pnt
            clipped = shape*Box(Pnt(-.1,-.1,z-thickness/2),Pnt(.1,.1,z+thickness/2))
            self.assertAlmostEqual(clipped.mass/expected,1.,places=9)

    def test_graph_sampling_control_is_not_a_cad_substitute(self):
        primitive = self.primitive()
        points = [(.01+.001*math.cos(t),-.004+.001*math.sin(t)) for t in np.linspace(0,math.pi/2,17)]
        points[0],points[-1] = primitive['start'],primitive['end']
        control = chord_control({'circular_arc_m':primitive,'points_m':points})
        self.assertTrue(control['passed'])
        self.assertGreater(control['relative_length_difference'],0.)
        points[8] = (.01,-.004)
        with self.assertRaisesRegex(ValueError,'off the actual CAD circle'):
            chord_control({'circular_arc_m':primitive,'points_m':points})

    def test_degenerate_arc_and_nonpositive_inner_radius_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'no straight/chord repair'):
            parameters(dict(start=[0.,0.],mid=[1.,0.],end=[2.,0.]))
        with self.assertRaisesRegex(ValueError,'inner arc radius'):
            solid(self.primitive(),0.,.003,35e-6)
