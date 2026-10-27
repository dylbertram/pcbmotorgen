import unittest

from check_spectral_biased_ac import refined_mesh,geometry_hash


class BiasedAcInputsTest(unittest.TestCase):
    def test_shared_source_is_not_refined_twice_by_bare_then_stack(self):
        shared={'mesh':0.02,'group':1}
        case={'period':12,'bands':[],'rects':[shared],'labels':[]}
        bare=refined_mesh(case,0.5);stack=refined_mesh(case,0.5)
        self.assertEqual(shared['mesh'],0.02)
        self.assertEqual(stack['rects'][0]['mesh'],0.01)
        self.assertEqual(geometry_hash(bare),geometry_hash(stack))


if __name__=='__main__':unittest.main()
