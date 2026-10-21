import unittest
from unittest.mock import patch

import numpy as np

from audit_finite_dc_winding_sections import probes


class WindingSectionProbeTest(unittest.TestCase):
    def test_native_arc_uses_saved_midpoint_and_tangent_not_a_chord_plane(self):
        root=np.sqrt(.5);primitive=dict(start=[.001,0.],mid=[.001*root,.001*root],end=[0.,.001])
        edges=[dict(geometry=dict(kind='trace',layer=0),points=[[0.,0.,-.0008],[.002,0.,-.0008]]),
            dict(geometry=dict(kind='via'),points=[[.002,0.,-.0008],[.002,0.,0.]]),
            dict(geometry=dict(kind='trace',layer=0,circular_arc_m=primitive),
                points=[[x,y,-.0008] for x,y in primitive.values()])]
        fixture=dict(sim={},drive={},geometry_hints={},networks=[dict(net='C',edges=edges)])
        spec=dict(layers=[dict(centre_z_m=-.0008,trace_width_m=.0002,thickness_m=35e-6)],
            via_outer_radius_m=.000175,via_barrel_area_m2=2.5525440310417068e-8)
        with patch('audit_finite_dc_winding_sections.dimensions',return_value=spec),\
            patch('audit_finite_dc_winding_sections.resistances',return_value=None),\
            patch('audit_finite_dc_winding_sections.unit_currents',return_value=([1.,1.,.5],1.)),\
            patch('audit_finite_dc_winding_sections.edge_points',side_effect=lambda edge,*args:np.asarray(edge['points'])):
            values=probes(fixture,np.array([0.,0.,.0008]),{'C':{'current_a':-1.}})
        arc=next(value for value in values if value['label'].startswith('arc:'))
        np.testing.assert_allclose(arc['centre'],[.001*root,.001*root,0.])
        np.testing.assert_allclose(arc['normal'],[-root,root,0.])
        self.assertEqual(arc['expected_per_loop_a'],-.5)

    def test_signed_vias_are_aggregated_and_trace_depth_is_preserved(self):
        fixture={'sim':{},'drive':{},'geometry_hints':{},'networks':[
            {'net':'A','edges':[
                {'geometry':{'kind':'trace','layer':0},'points':[[0,0,0],[.002,0,0]]},
                {'geometry':{'kind':'via'},'points':[[.002,0,0],[.002,0,-.0008]]}]},
            {'net':'B','edges':[
                {'geometry':{'kind':'trace','layer':0},'points':[[0,.002,0],[.002,.002,0]]},
                {'geometry':{'kind':'via'},'points':[[.002,.002,0],[.002,.002,-.0008]]}]}]}
        spec={'layers':[{'trace_width_m':.0002,'thickness_m':35e-6}],
            'via_outer_radius_m':.000175,'via_barrel_area_m2':2.5525440310417068e-8}
        with patch('audit_finite_dc_winding_sections.dimensions',return_value=spec),\
                patch('audit_finite_dc_winding_sections.resistances',return_value=None),\
                patch('audit_finite_dc_winding_sections.unit_currents',return_value=([1.,1.],1.)),\
                patch('audit_finite_dc_winding_sections.edge_points',side_effect=lambda edge,*args:np.asarray(edge['points'])):
            values=probes(fixture,np.array([0,0,.0008]),{'A':{'current_a':1.},'B':{'current_a':-1.}})
        self.assertEqual(len(values),4)
        traces=[p for p in values if p['label'].startswith('trace')]
        vias=[p for p in values if p['label'].startswith('via')]
        self.assertEqual([p['centre'][2] for p in traces],[.0008,.0008])
        self.assertEqual([p['centre'][2] for p in vias],[.0004,.0004])
        self.assertEqual([p['expected_per_loop_a'] for p in vias],[-1.,1.])

    def test_all_eligible_is_not_silently_limited_to_historical_sample(self):
        edges=[{'geometry':{'kind':'trace','layer':0},'points':[[0,i*.001,0],[.002,i*.001,0]]} for i in range(12)]
        edges += [{'geometry':{'kind':'via'},'points':[[i*.001,0,0],[i*.001,0,-.0008]]} for i in range(20)]
        fixture={'sim':{},'drive':{},'geometry_hints':{},'networks':[{'net':'A','edges':edges}]}
        spec={'layers':[{'trace_width_m':.0002,'thickness_m':35e-6}],
              'via_outer_radius_m':.000175,'via_barrel_area_m2':2.5525440310417068e-8}
        with patch('audit_finite_dc_winding_sections.dimensions',return_value=spec),\
                patch('audit_finite_dc_winding_sections.resistances',return_value=None),\
                patch('audit_finite_dc_winding_sections.unit_currents',return_value=([1.]*len(edges),1.)),\
                patch('audit_finite_dc_winding_sections.edge_points',side_effect=lambda edge,*args:np.asarray(edge['points'])):
            historical=probes(fixture,np.zeros(3),{'A':{'current_a':1.}})
            all_values=probes(fixture,np.zeros(3),{'A':{'current_a':1.}},all_eligible=True)
        self.assertEqual(len(historical),18)
        self.assertEqual(len(all_values),32)
        self.assertEqual(len({p['label'] for p in all_values}),32)
