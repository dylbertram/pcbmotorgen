import copy
import unittest

from check_convergence import refined


class IndependentMeshTest(unittest.TestCase):
    def test_near_mesh_air_mesh_and_boundary_are_independent(self):
        case={'name':'original','bands':[{'y0':-40,'y1':0,'mesh':0},{'y0':0,'y1':1,'mesh':0.08},
                                      {'y0':1,'y1':41,'mesh':0}],
              'rects':[{'mesh':0.1}],'labels':[{'mesh':0.15}]}
        original=copy.deepcopy(case)
        half=refined(case,'half',0.5)
        domain=refined(case,'domain',0.5,60)
        air=refined(case,'air',0.5,air_mesh=0.5)
        self.assertEqual(case,original)
        self.assertEqual(half['rects'][0]['mesh'],0.05)
        self.assertEqual(half['bands'][1]['mesh'],0.04)
        self.assertEqual(half['bands'][0]['mesh'],1.0)
        self.assertEqual(domain['bands'][0]['mesh'],half['bands'][0]['mesh'])
        self.assertEqual(domain['bands'][0]['y0'],-60)
        self.assertEqual(domain['bands'][-1]['y1'],61)
        self.assertEqual(air['bands'][0]['mesh'],0.5)
        self.assertEqual(air['rects'],half['rects'])


if __name__=='__main__':
    unittest.main()
