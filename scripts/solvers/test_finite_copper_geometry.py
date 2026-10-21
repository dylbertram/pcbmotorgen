import importlib.util
import unittest

import numpy as np

from finite_copper_geometry import dimensions,trace_solid,build


class FiniteCopperDimensionsTest(unittest.TestCase):
    def fixture(self):
        return {'sim':{'num_layers':4,'pcb_thickness_m':.0008,'min_trace_m':.0002,'min_via_drill_m':.0003,'min_via_annular_ring_m':.0001},
            'drive':{'outer_copper_oz':1.,'inner_copper_oz':2.,'via_plating_m':.000025,'winding_temp_c':75.},
            'geometry_hints':{'layer_z_m':[-.0008,-.0005,-.0003,0.]}}

    def test_saved_width_weight_plating_and_nonuniform_depths_are_used(self):
        result=dimensions(self.fixture());self.assertEqual([x['centre_z_m'] for x in result['layers']],[-.0008,-.0005,-.0003,0.])
        np.testing.assert_allclose([x['thickness_m'] for x in result['layers']],[35e-6,70e-6,70e-6,35e-6])
        self.assertAlmostEqual(result['via_barrel_area_m2'],np.pi*25e-6*(.0003+25e-6))
        self.assertAlmostEqual(result['via_pad_radius_m'],.00025)
        self.assertGreater(result['copper_resistivity_ohm_m'],1.724e-8)

    @unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned OCCT environment required')
    def test_finite_straight_trace_has_saved_cross_section_and_round_caps(self):
        length=.01;width=.0002;thickness=35e-6;solid=trace_solid([[0.,0.,0.],[length,0.,0.]],width,thickness)
        expected=(length*width+np.pi*(width/2)**2)*thickness
        self.assertAlmostEqual(float(solid.mass)/expected,1.,places=9)

    @unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned OCCT environment required')
    def test_trace_pad_and_hollow_barrel_form_a_connected_finite_conductor(self):
        from netgen.occ import Cylinder,Pnt,Dir
        fixture=self.fixture();fixture['sim']['num_layers']=2;fixture['geometry_hints']={'layer_z_m':[0.,-.0008]}
        fixture['networks']=[{'net':'A','edges':[
            {'geometry':{'kind':'trace','layer':0,'points_m':[[0.,0.],[.001,0.]]}},
            {'geometry':{'kind':'via','layers':[0,1],'position_m':[.001,0.]}},
            {'geometry':{'kind':'trace','layer':1,'points_m':[[.001,0.],[.002,0.]]}}]}]
        copper,metadata=build(fixture,[0.,0.,0.])
        self.assertEqual(metadata['solid_components'],1);self.assertEqual(metadata['distinct_via_positions'],1)
        bore=Cylinder(Pnt(.001,0.,-.0009),Dir(0,0,1),.000149,.001)
        self.assertLess(abs(float((copper*bore).mass)),1e-20)
