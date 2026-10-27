import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ngsolve_reduced import seed_response


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class ResponseSeedTest(unittest.TestCase):
    def test_cross_mesh_seed_is_supported_only_inside_the_old_domain(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        old=ng.Mesh(OCCGeometry(Box(Pnt(0,0,0),Pnt(1,1,1))).GenerateMesh(maxh=.2))
        new=ng.Mesh(OCCGeometry(Box(Pnt(0,0,0),Pnt(2,2,2))).GenerateMesh(maxh=.2))
        oldfes=ng.H1(old,order=2);oldsol=ng.GridFunction(oldfes);oldsol.Set(ng.x*ng.y+ng.z)
        newsol=ng.GridFunction(ng.H1(new,order=2))
        seed={'model':{'test':1},'quarter_symmetry':False,'order':2,'linear_material':False,'air_radius_m':1.}
        source={'model':{'test':1},'quarter_symmetry':False}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'summary.json').write_text('seed');(root/'psi.sol').write_text('seed')
            with patch('ngsolve_reduced.load_solution',return_value=(ng,seed,old,oldfes,oldsol)):
                info=seed_response(ng,new,newsol,root,source,2,False)
                self.assertEqual(info['taper_radii_m'],[.8,.9])
                self.assertAlmostEqual(float(newsol(new(.05,.05,.05))),.0525,places=10)
                self.assertAlmostEqual(float(newsol(new(1.5,1.5,1.5))),0.,places=12)
                with self.assertRaisesRegex(ValueError,'different physical'):
                    seed_response(ng,new,newsol,root,dict(source,model={'test':2}),2,False)
