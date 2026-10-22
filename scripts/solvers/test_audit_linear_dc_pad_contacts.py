from copy import deepcopy
import unittest

import numpy as np

from audit_linear_dc_pad_contacts import cylinder_clearance,witnesses
import test_dc_request_contract as fixtures


class PadContactWitnessTest(unittest.TestCase):
    def fixture(self,distance=.0004):
        _,fixture,_,_=fixtures.LiveDcRequestTest().inputs()
        template=dict(a=0,b=1,geometry=dict(kind='via',position_m=[0.,0.],layers=[0,1]))
        fixture['networks']=[]
        for net,x in [('A',0.),('B',distance)]:
            edge=deepcopy(template);edge.update(a=0,b=1);edge['geometry']['position_m']=[x,0.]
            edge['geometry']['layers']=[0,1]
            fixture['networks'].append(dict(net=net,edges=[edge],star=[2]))
        return fixture

    def test_positive_ball_proves_overlap_but_does_not_change_fixture(self):
        fixture=self.fixture();before=deepcopy(fixture);found=witnesses(fixture,[0,0,0])
        self.assertEqual(len(found),2);self.assertGreater(found[0]['positive_contact_ball_radius_m'],0)
        self.assertEqual(fixture,before)

    def test_clearance_and_intended_star_pairs_are_not_contact_witnesses(self):
        self.assertEqual(witnesses(self.fixture(.001),[0,0,0]),[])
        fixture=self.fixture();fixture['networks'][0]['star']=[1]
        self.assertEqual(witnesses(fixture,[0,0,0]),[])

    def test_global_bore_through_midpoint_removes_contact_witness(self):
        fixture=self.fixture();third=deepcopy(fixture['networks'][0]);third['net']='C';third['star']=[1]
        third['edges'][0]['geometry']['position_m']=[.0002,0.];fixture['networks'].append(third)
        self.assertEqual(witnesses(fixture,[0,0,0]),[])

    def test_approved_smaller_drill_preserves_ring_and_removes_known_pad_witness(self):
        fixture=self.fixture();before=deepcopy(fixture)
        self.assertTrue(witnesses(fixture,[0,0,0]))
        fixture['sim']['min_via_drill_m']=.00015
        self.assertEqual(witnesses(fixture,[0,0,0]),[])
        self.assertEqual(fixture['sim']['min_via_annular_ring_m'],before['sim']['min_via_annular_ring_m'])
        self.assertEqual(fixture['networks'],before['networks'])

    def test_cylinder_distance_respects_finite_depth(self):
        self.assertEqual(cylinder_clearance(np.array([0.,0.,2.]),np.array([0.,0.]),1.,0.,1.),1.)
        self.assertLess(cylinder_clearance(np.array([0.,0.,.5]),np.array([0.,0.]),1.,0.,1.),0.)
