import unittest
import importlib.util

import numpy as np
import magpylib as magpy

from closed_wire_source import validate,fields,coefficient,MU0


class ClosedWireSourceTest(unittest.TestCase):
    def setUp(self):
        self.path=np.array([[-.006,-.006,0.],[.006,-.006,0.],[.006,.006,0.],[-.006,.006,0.],[-.006,-.006,0.]])
        self.segments=np.stack([self.path[:-1],self.path[1:]],axis=1)
        self.currents=np.ones(4)

    def test_biot_savart_matches_independent_polyline_kernel(self):
        points=np.array([[0.,0.,.003],[.002,.001,.004],[-.003,.002,-.001],[.01,-.006,0.]])
        actual,_=fields(points,self.segments,self.currents)
        from scipy.constants import mu_0
        # Magpylib uses the measured SI mu0, while these solver prototypes
        # consistently use the historical 4*pi*1e-7. Compare kernels using
        # the same declared constant, rather than weakening the assertion.
        expected=magpy.current.Polyline(current=1.,vertices=self.path).getB(points)*MU0/mu_0
        np.testing.assert_allclose(actual,expected,rtol=1e-11,atol=1e-14)

    def test_curl_of_vector_potential_matches_B(self):
        point=np.array([.002,.001,.004]);step=1e-7;gradient=[]
        for axis in range(3):
            offset=np.eye(3)[axis]*step
            gradient.append((fields(np.array([point+offset]),self.segments,self.currents)[1][0]-fields(np.array([point-offset]),self.segments,self.currents)[1][0])/(2*step))
        dx,dy,dz=gradient;curl=np.array([dy[2]-dz[1],dz[0]-dx[2],dx[1]-dy[0]])
        np.testing.assert_allclose(curl,fields(np.array([point]),self.segments,self.currents)[0][0],rtol=1e-7,atol=1e-12)

    def test_open_returns_and_self_observations_are_not_silently_repaired(self):
        with self.assertRaisesRegex(ValueError,'Open current'):validate(self.segments[:-1],self.currents[:-1])
        with self.assertRaisesRegex(ValueError,'singular'):fields(np.array([[0.,-.006,0.]]),self.segments,self.currents)

    @unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
    def test_compiled_source_matches_numpy_fields(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        mesh=ng.Mesh(OCCGeometry(Box(Pnt(-.02,-.02,-.02),Pnt(.02,.02,.02))).GenerateMesh(maxh=.02))
        points=np.array([[0.,0.,.003],[.002,.001,.004],[-.003,.002,-.001],[.01,-.006,0.]])
        expected_b,expected_a=fields(points,self.segments,self.currents)
        b,a=coefficient(ng,self.segments,self.currents)
        mapped=mesh(points[:,0],points[:,1],points[:,2])
        np.testing.assert_allclose(np.asarray(b(mapped)).reshape(-1,3),expected_b,rtol=1e-12,atol=1e-14)
        np.testing.assert_allclose(np.asarray(a(mapped)).reshape(-1,3),expected_a,rtol=1e-12,atol=1e-14)
