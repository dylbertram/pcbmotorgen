import unittest

from finite_copper_geometry import build as original_build
from finite_copper_single_drill import build
import test_finite_copper_geometry as geometry_fixtures


class SingleDrillCopperTest(unittest.TestCase):
    def test_boolean_order_keeps_dimensions_and_drills(self):
        from netgen.occ import Cylinder,Pnt,Dir
        fixture=geometry_fixtures.FiniteCopperDimensionsTest().fixture();fixture['sim']['num_layers']=2
        fixture['geometry_hints']={'layer_z_m':[0.,-.0008]}
        fixture['networks']=[dict(net='A',edges=[
            dict(geometry=dict(kind='trace',layer=0,points_m=[[0.,0.],[.001,0.]])),
            dict(geometry=dict(kind='via',layers=[0,1],position_m=[.001,0.])),
            dict(geometry=dict(kind='trace',layer=1,points_m=[[.001,0.],[.002,0.]]))])]
        original,before=original_build(fixture,[0.,0.,0.]);actual,after=build(fixture,[0.,0.,0.])
        self.assertEqual(after['solid_components'],1)
        self.assertAlmostEqual(actual.mass/original.mass,1.,places=8)
        for key in before:
            if key!='volume_m3':self.assertEqual(after[key],before[key])
        bore=Cylinder(Pnt(.001,0.,-.0009),Dir(0,0,1),.000149,.001)
        self.assertLess(abs(float((actual*bore).mass)),1e-20)
