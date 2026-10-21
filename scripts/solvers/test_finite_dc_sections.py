import importlib.util
import json
import unittest

import numpy as np

from audit_finite_dc_sections import section,tetrahedra,clip_polygon


class ClipTest(unittest.TestCase):
    def test_half_plane_clips_polygon(self):
        p=clip_polygon(np.array([[-1.,-1.],[1.,-1.],[1.,1.],[-1.,1.]]),0,.5,1)
        self.assertEqual(len(p),4);self.assertAlmostEqual(p[:,0].max(),.5)

    def test_coplanar_internal_face_is_counted_once(self):
        face=[[0.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
        tets=np.array([[*face,[-1.,0.,0.]],[*face,[1.,0.,0.]]])
        value=section(lambda *point:point,lambda point:(1.,0.,0.),tets,[0.,.3,.3],[1.,0.,0.],2.)
        self.assertAlmostEqual(value['area_m2'],.5)
        self.assertAlmostEqual(value['current_a'],.5)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve required')
class SectionTest(unittest.TestCase):
    def test_exact_linear_current_on_clipped_box(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        mesh=ng.Mesh(OCCGeometry(Box(Pnt(0,0,0),Pnt(1,1,1))).GenerateMesh(maxh=.3));mesh.Curve(1)
        current=ng.CoefficientFunction((2+ng.x,0,0));tets=tetrahedra(mesh)
        for sign in [-1,1]:
            value=section(mesh,current,tets,[.371,.5,.5],[sign,0,0],.2)
            self.assertAlmostEqual(value['area_m2'],.16,places=12)
            self.assertAlmostEqual(value['current_a'],sign*2.371*.16,places=12)
            json.dumps(dict(value,passed=value['current_a']>0),allow_nan=False)

    def test_empty_section_rejected(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        mesh=ng.Mesh(OCCGeometry(Box(Pnt(0,0,0),Pnt(1,1,1))).GenerateMesh(maxh=.5))
        with self.assertRaisesRegex(ValueError,'Empty'):
            section(mesh,ng.CoefficientFunction((1,0,0)),tetrahedra(mesh),[2,0,0],[1,0,0],.1)
