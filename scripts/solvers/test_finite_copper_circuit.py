import importlib.util
import unittest

from finite_copper_circuit import return_prism,drive_segment


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned OCCT environment required')
class FiniteReturnGeometryTest(unittest.TestCase):
    def test_drive_port_stays_clear_of_bend_junctions(self):
        import numpy as np
        points=np.array([[0.,0.,0.],[-.001,0.,.001],[-.001,.001,.001],[0.,.001,0.]])
        start,end=drive_segment(points,.0002,.5)
        self.assertAlmostEqual(np.linalg.norm(end-start),.0005)
        self.assertGreater(np.linalg.norm(start-points[1]),.0001)
        with self.assertRaisesRegex(ValueError,'avoid widened'):drive_segment(points,.0002,1.)
        old_port=return_prism(points[1],points[2],.0002,35e-6)
        new_port=return_prism(start,end,.0002,35e-6)
        for a,b in [(points[0],points[1]),(points[2],points[3])]:
            bend=return_prism(a,b,.0002,35e-6)
            self.assertGreater(float((old_port*bend).mass),0.)
            self.assertLess(abs(float((new_port*bend).mass)),1e-20)

    def test_saved_cross_section_is_retained_for_horizontal_and_sloped_return(self):
        import numpy as np
        width=.0002;thickness=35e-6
        for end in [[.002,0.,0.],[.002,0.,.001],[0.,0.,.001]]:
            shape=return_prism([0.,0.,0.],end,width,thickness)
            self.assertAlmostEqual(float(shape.mass)/(np.linalg.norm(end)*width*thickness),1.,places=9)
