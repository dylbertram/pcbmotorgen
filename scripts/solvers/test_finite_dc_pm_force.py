import importlib.util
import unittest

import numpy as np

from audit_finite_dc_pm_force import sources


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve required')
class FiniteCurrentSourcesTest(unittest.TestCase):
    def test_streamed_affine_sources_reproduce_volume_and_linear_current(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        mesh=ng.Mesh(OCCGeometry(Box(Pnt(0,0,0),Pnt(1,1,1))).GenerateMesh(maxh=.4));mesh.Curve(1)
        current=ng.CoefficientFunction((ng.x,ng.y,ng.z))
        for degree in [2,4]:
            volume=0.;net=np.zeros(3);loss=0.;batches=0
            for points,j,weights in sources(ng,mesh,current,degree,batch_cells=3):
                self.assertLessEqual(len(points),3*len(ng.IntegrationRule(ng.ET.TET,degree)))
                volume+=weights.sum();net+=(j*weights[:,None]).sum(axis=0)
                loss+=weights@np.sum(j*j,axis=1);batches+=1
            self.assertGreater(batches,1);self.assertAlmostEqual(volume,1.)
            np.testing.assert_allclose(net,[.5,.5,.5],rtol=1e-12,atol=1e-12)
            self.assertAlmostEqual(loss,1.)

    def test_curved_volume_weights_are_rejected(self):
        import ngsolve as ng
        from netgen.occ import Sphere,Pnt,OCCGeometry
        mesh=ng.Mesh(OCCGeometry(Sphere(Pnt(0,0,0),1.)).GenerateMesh(maxh=.7));mesh.Curve(2)
        with self.assertRaisesRegex(ValueError,'curved'):
            list(sources(ng,mesh,ng.CoefficientFunction((1,0,0)),2))
