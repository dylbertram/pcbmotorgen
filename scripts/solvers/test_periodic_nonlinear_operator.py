import importlib.util
import unittest

import numpy as np

from ngsolve_periodic_ac import energy,symmetric_triangle_rule,MU0
from periodic_nonlinear_operator import ExplicitNonlinearPlate


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class ExplicitPeriodicOperatorTest(unittest.TestCase):
    def test_gradient_and_full_tangent_match_automatic_energy_on_both_branches(self):
        import ngsolve as ng
        from netgen.geom2d import SplineGeometry
        geometry=SplineGeometry();geometry.AddRectangle((0.,0.),(.003,.002),bc='outer');geometry.SetMaterial(1,'plate')
        mesh=ng.Mesh(geometry.GenerateMesh(maxh=.001));space=ng.H1(mesh,order=2);trial=space.TrialFunction()
        state=ng.GridFunction(space);state.vec.FV().NumPy()[:]=np.linspace(0.,1e-7,space.ndof)
        bx=ng.CoefficientFunction(.02);parameter=ng.Parameter(.001);bz=parameter+ng.x
        rule=symmetric_triangle_rule(ng,8);dx=ng.dx(definedon=mesh.Materials('plate'),intrules={ng.ET.TRIG:rule})
        for strength in [.001,.3]:
            parameter.Set(strength)
            for rate in [0.,2e7]:
                automatic=ng.BilinearForm(space,symmetric=True)
                density=energy(ng,bx+ng.grad(trial)[1],bz+ng.grad(trial)[0],130.,.25)-(bx*ng.grad(trial)[1]+bz*ng.grad(trial)[0])/MU0
                automatic+=ng.Variation(density*dx)
                if rate:automatic+=ng.Variation((.5*rate*.2*trial**2)*dx)
                explicit=ExplicitNonlinearPlate(ng,space,mesh,bx,bz,130.,.25,.2,rule,rate)
                a=state.vec.CreateVector();b=state.vec.CreateVector();automatic.Apply(state.vec,a);explicit.Apply(state.vec,b)
                np.testing.assert_allclose(a.FV().NumPy(),b.FV().NumPy(),rtol=1e-11,atol=1e-12)
                automatic.AssembleLinearization(state.vec);explicit.AssembleLinearization(state.vec)
                direction=state.vec.CreateVector();direction.FV().NumPy()[:]=np.linspace(.1,.2,space.ndof)
                a.data=automatic.mat*direction;b.data=explicit.mat*direction
                np.testing.assert_allclose(a.FV().NumPy(),b.FV().NumPy(),rtol=1e-11,atol=1e-9)
