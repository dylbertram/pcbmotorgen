import importlib.util
import unittest

import numpy as np

from finite_copper_primal import solve,saved_resistivity,verify_potential_artifact


class PrimalInputBindingTest(unittest.TestCase):
    def test_saved_resistivity_cannot_be_fitted_and_potential_bytes_are_bound(self):
        import json
        from pathlib import Path
        import tempfile
        from post_project_force import sha
        for count in [-1,6,True]:
            with self.subTest(corrections=count),self.assertRaisesRegex(ValueError,'Bounded'):
                solve(None,None,None,1.,max_corrections=count)
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);geometry=work/'summary.json'
            geometry.write_text(json.dumps({'geometry':{'copper_resistivity_ohm_m':2.0966426e-8}}))
            source={'input_hashes':{str(work/'copper.brep'):'cad',str(geometry):sha(geometry)}}
            self.assertEqual(saved_resistivity(source,2.0966426e-8),geometry)
            with self.assertRaisesRegex(ValueError,'no fitted value'):
                saved_resistivity(source,2e-8)
            potential=work/'potential.sol';potential.write_bytes(b'potential-fixture')
            report={'potential_sha256':sha(potential)};verify_potential_artifact(work,report)
            with self.assertRaisesRegex(ValueError,'provenance'):
                verify_potential_artifact(work,{})
            potential.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'provenance'):
                verify_potential_artifact(work,report)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class PrimalDCCheckTest(unittest.TestCase):
    def test_annulus_matches_dc_analytic_power_and_mean_current(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry
        inner=.001;outer=.002;height=.0005
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        ring.mat('copper');mesh=ng.Mesh(OCCGeometry(ring).GenerateMesh(maxh=.00025));mesh.Curve(2)
        electric=ng.CoefficientFunction((-ng.y,ng.x,0.))/(2*np.pi*(ng.x**2+ng.y**2))
        _,metadata=solve(ng,mesh,electric,1.)
        self.assertLess(abs(metadata['source_power_w']/(height*np.log(outer/inner)/(2*np.pi))-1),.02)
        self.assertLess(metadata['net_current_relative_error'],1e-9)
