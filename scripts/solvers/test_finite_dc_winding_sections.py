import unittest
from unittest.mock import patch

import numpy as np

from audit_finite_dc_winding_sections import probes


class WindingSectionProbeTest(unittest.TestCase):
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
