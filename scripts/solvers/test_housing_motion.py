import copy
import importlib.util
import unittest

import numpy as np

from ngsolve_housing_motion import profile,moving_source,source_electric,cross
from reduced_potential import source_field


class MotionProfileTest(unittest.TestCase):
    def test_reverse_motion_has_mirrored_endpoints_and_identical_duration(self):
        x,t,dt=profile(20.,.12,240)
        y,u,du=profile(-20.,.12,240)
        self.assertAlmostEqual(x,-.06);self.assertAlmostEqual(x+20*t,.06)
        self.assertAlmostEqual(y,.06);self.assertAlmostEqual(y-20*u,-.06)
        self.assertEqual(t,u);self.assertEqual(dt,du)

    def test_zero_speed_is_a_static_source_not_an_oscillating_magnet(self):
        x,t,_=profile(0.,.12,4)
        self.assertEqual(x,x+0*t)
        with self.assertRaises(ValueError):profile(float('nan'),.12,4)
        with self.assertRaises(ValueError):profile(20.,0.,4)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class MovingFieldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        cls.ng=ng
        cls.mesh=ng.Mesh(OCCGeometry(Box(Pnt(-.004,-.004,-.0013),Pnt(.004,.004,-.0003))).GenerateMesh(maxh=.003))

    def test_parameter_translation_matches_cuboid_source_without_mutating_model(self):
        ng=self.ng;model={'magnets':[{'origin_m':[-.0025,-.0025,.0013],'size_m':[.005,.005,.003],'polarization_t':[0,0,1.34]}]}
        original=copy.deepcopy(model);shift=ng.Parameter(0.);field=moving_source(ng,model,shift)
        points=np.array([[.0001,.0002,-.0008],[.001,.002,-.001]])
        expected=source_field(model)
        for offset in [0.,.003,-.003]:
            shift.Set(offset)
            actual=np.asarray(field(self.mesh(points[:,0],points[:,1],points[:,2]))).reshape(-1,3)
            np.testing.assert_allclose(actual,expected(points-np.array([offset,0.,0.])),rtol=1e-10,atol=1e-12)
        self.assertEqual(model,original)

    def test_source_faraday_sign_and_mechanical_work_are_consistent(self):
        ng=self.ng;speed=2.;b=ng.CoefficientFunction((.2,.3,.4));j=ng.CoefficientFunction((1.,2.,3.))
        point=self.mesh(.0001,.0002,-.0008)
        electric=np.asarray(source_electric(ng,b,speed)(point)).reshape(3)
        force=np.asarray(cross(ng,j,b)(point)).reshape(3)
        self.assertAlmostEqual(float(np.dot([1.,2.,3.],electric)),speed*force[0])
        # B=(z,0,x) is curl-free and divergence-free. Rigid +x translation
        # gives dBz/dt=-v, requiring curl(E)_z=+v.
        e=source_electric(ng,ng.CoefficientFunction((ng.z,0.,ng.x)),speed)
        h=1e-6
        derivative=(np.asarray(e(self.mesh(.0001+h,.0002,-.0008)))-np.asarray(e(self.mesh(.0001-h,.0002,-.0008))))/(2*h)
        self.assertAlmostEqual(float(derivative.reshape(3)[1]),speed,places=10)
