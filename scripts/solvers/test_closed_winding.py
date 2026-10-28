import unittest

import numpy as np

from closed_winding import build
from closed_wire_source import validate


def fixture():
    networks=[]
    for phase,y in [('A',0.),('B',.001)]:
        networks.append({'net':phase,'node_count':2,'terminal':[0],'star':[1],
            'edges':[{'a':0,'b':1,'geometry':{'kind':'trace','layer':0,'points_m':[[0.,y],[.01,.002]]}}]})
    return {'networks':networks,'sim':{'num_layers':1,'pcb_thickness_m':.0008,'min_trace_m':.0002},
        'drive':{'winding_temp_c':20.,'inner_copper_oz':1.,'outer_copper_oz':1.},'geometry_hints':{}}


class ClosedWindingTest(unittest.TestCase):
    def test_balanced_current_has_closed_geometric_return(self):
        segments,currents,report=build(fixture(),'A','B',[0.,0.,.0008],[[-.002,.001,.003],[-.002,0.,.003]])
        self.assertEqual(len(segments),5)
        self.assertEqual(validate(segments,currents)[2],0.)
        self.assertEqual(report['phase_data']['A']['current_a'],1.)
        self.assertEqual(report['phase_data']['B']['current_a'],-1.)
        np.testing.assert_allclose(report['return_path_m'][0],[0.,.001,.0008])
        np.testing.assert_allclose(report['return_path_m'][-1],[0.,0.,.0008])

    def test_missing_or_unconnected_returns_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'return waypoints'):build(fixture(),'A','B',[0.,0.,0.],[])
        changed=fixture();changed['networks'][1]['edges'][0]['geometry']['points_m'][-1][0]=.011
        with self.assertRaisesRegex(ValueError,'star connectivity'):build(changed,'A','B',[0.,0.,0.],[[0.,0.,.003]])
