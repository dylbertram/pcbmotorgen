import importlib.util
import unittest

import numpy as np

from newton_factor import NewtonFactor


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class NewtonFactorTest(unittest.TestCase):
    def test_fixed_reference_does_not_replace_the_changed_operator(self):
        import ngsolve as ng
        from netgen.geom2d import unit_square
        mesh=ng.Mesh(unit_square.GenerateMesh(maxh=.25));space=ng.H1(mesh,order=2,dirichlet='.*');u,v=space.TnT()
        reference=ng.BilinearForm(space,symmetric=True);reference+=(ng.InnerProduct(ng.grad(u),ng.grad(v))+u*v)*ng.dx;reference.Assemble()
        parameter=ng.Parameter(1.);matrix=ng.BilinearForm(space,symmetric=True);matrix+=(parameter*ng.InnerProduct(ng.grad(u),ng.grad(v))+u*v)*ng.dx
        rhs=ng.GridFunction(space).vec.CreateVector();rhs.FV().NumPy()[:]=np.linspace(0.,1.,space.ndof)
        factor=NewtonFactor(ng,reference.mat.Inverse(space.FreeDofs(),inverse='sparsecholesky'))
        for value in [1.,.1,.01]:
            parameter.Set(value);matrix.Assemble();result=factor.solve(matrix.mat,rhs,space.FreeDofs())
            exact=rhs.CreateVector();exact.data=matrix.mat.Inverse(space.FreeDofs(),inverse='sparsecholesky')*rhs
            np.testing.assert_allclose(result.FV().NumPy(),exact.FV().NumPy(),rtol=1e-10,atol=1e-12)
        self.assertEqual(factor.stats['factorizations'],1)

    def test_reused_factor_solves_changed_matrix_not_a_frozen_equation(self):
        import ngsolve as ng
        from netgen.geom2d import unit_square
        mesh=ng.Mesh(unit_square.GenerateMesh(maxh=.25));space=ng.H1(mesh,order=2,dirichlet='.*');u,v=space.TnT();parameter=ng.Parameter(1.)
        matrix=ng.BilinearForm(space,symmetric=True);matrix+=(parameter*ng.InnerProduct(ng.grad(u),ng.grad(v))+u*v)*ng.dx
        rhs=ng.GridFunction(space).vec.CreateVector();rhs.FV().NumPy()[:]=np.linspace(0.,1.,space.ndof)
        factor=NewtonFactor(ng)
        for strength in [1.,3.,.5]:
            parameter.Set(strength);matrix.Assemble();result=factor.solve(matrix.mat,rhs,space.FreeDofs())
            exact=rhs.CreateVector();exact.data=matrix.mat.Inverse(space.FreeDofs(),inverse='sparsecholesky')*rhs
            np.testing.assert_allclose(result.FV().NumPy(),exact.FV().NumPy(),rtol=1e-10,atol=1e-12)
        self.assertEqual(factor.stats['solves'],3);self.assertEqual(factor.stats['factorizations'],1)
        self.assertLessEqual(factor.stats['maximum_relative_linear_residual'],1e-9)
