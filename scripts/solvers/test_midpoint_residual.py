import importlib.util
import unittest

import numpy as np

from midpoint_residual import evaluate


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class MidpointResidualTest(unittest.TestCase):
    def test_stationary_nonzero_bias_keeps_exactly_zero_mass_increment(self):
        import ngsolve as ng
        from netgen.geom2d import unit_square
        mesh=ng.Mesh(unit_square.GenerateMesh(maxh=.5));space=ng.H1(mesh,order=1);u,v=space.TnT()
        mass=ng.BilinearForm(space);mass+=1e12*u*v*ng.dx;mass.Assemble()
        state=ng.GridFunction(space);state.vec.FV().NumPy()[:]=np.linspace(.1,.2,space.ndof)
        source=state.vec.CreateVector();source[:]=0.;result=state.vec.CreateVector()
        class ZeroGradient:
            def Apply(self,vector,out):out[:]=0.
        evaluate(ZeroGradient(),mass.mat,state.vec,state.vec,source,0.,1e-8,result)
        np.testing.assert_array_equal(result.FV().NumPy(),0.)

    def test_state_difference_mass_matches_the_unscaled_equation(self):
        import ngsolve as ng
        from netgen.geom2d import unit_square
        mesh=ng.Mesh(unit_square.GenerateMesh(maxh=.5));space=ng.H1(mesh,order=1);u,v=space.TnT()
        mass=ng.BilinearForm(space);mass+=u*v*ng.dx;mass.Assemble()
        previous=ng.GridFunction(space);mid=ng.GridFunction(space);previous.vec.FV().NumPy()[:]=.1;mid.vec.FV().NumPy()[:]=.1001
        forcing=mid.vec.CreateVector();forcing.FV().NumPy()[:]=.01;result=mid.vec.CreateVector()
        class IdentityGradient:
            def Apply(self,vector,out):out.data=vector
        evaluate(IdentityGradient(),mass.mat,mid.vec,previous.vec,forcing,.2,.001,result)
        expected=mid.vec.CreateVector();difference=mid.vec.CreateVector();difference.FV().NumPy()[:]=mid.vec.FV().NumPy()-previous.vec.FV().NumPy()
        expected.data=mid.vec+2000*(mass.mat*difference)-.2*forcing
        np.testing.assert_allclose(result.FV().NumPy(),expected.FV().NumPy(),rtol=1e-13,atol=1e-14)
