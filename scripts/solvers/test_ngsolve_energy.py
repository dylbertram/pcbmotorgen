import importlib.util
import unittest
import copy

import numpy as np

import test_project_static


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned independent NGSolve environment')
class NGSolveEnergyTest(unittest.TestCase):
    def test_cached_source_keeps_the_energy_gradient_and_automatic_tangent(self):
        self.check_energy(1.)

    def test_unsaturated_branch_keeps_the_energy_gradient_and_tangent(self):
        self.check_energy(1e-5)

    def check_energy(self,source_scale):
        import ngsolve as ng
        from netgen.occ import Box, Pnt, OCCGeometry
        from ngsolve_reduced import energy_form
        from reduced_potential import response_model, source_field
        ng.SetNumThreads(1)
        box=Box(Pnt(0,0,-.0002),Pnt(.004,.004,0));box.mat('layer_0');box.bc('outer')
        mesh=ng.Mesh(OCCGeometry(box).GenerateMesh(maxh=.002))
        fes=ng.H1(mesh,order=2,dirichlet='outer');gfu=ng.GridFunction(fes)
        model=copy.deepcopy(test_project_static.ProjectStaticTest().model())
        for magnet in model['magnets']:magnet['polarization_t'][2]*=source_scale
        solver=response_model(model,True,True)
        form,bsource=energy_form(ng,mesh,fes,model,solver,False,4)
        points=np.array([[.001,.001,-.0001],[.002,.002,-.00015]])
        observed=np.asarray(bsource(mesh(points[:,0],points[:,1],points[:,2])))
        np.testing.assert_allclose(observed,source_field(model)(points),atol=1e-12,rtol=1e-10)
        free=np.array(fes.FreeDofs(),dtype=bool)
        self.assertGreater(np.count_nonzero(free),0)
        rng=np.random.default_rng(2026)
        gfu.vec.FV().NumPy()[:]=rng.normal(size=fes.ndof)*.001*free
        direction=gfu.vec.CreateVector();direction.FV().NumPy()[:]=rng.normal(size=fes.ndof)*.01*free
        residual=gfu.vec.CreateVector();plus=gfu.vec.CreateVector();minus=gfu.vec.CreateVector()
        plus.data=gfu.vec+.01*direction;minus.data=gfu.vec-.01*direction
        form.Apply(gfu.vec,residual)
        derivative=float(ng.InnerProduct(residual,direction))
        fd=(form.Energy(plus)-form.Energy(minus))/.02
        self.assertLess(abs(fd-derivative)/max(abs(derivative),1e-12),1e-5)
        form.AssembleLinearization(gfu.vec)
        jacobian=gfu.vec.CreateVector();jacobian.data=form.mat*direction
        rp=gfu.vec.CreateVector();rm=gfu.vec.CreateVector()
        form.Apply(plus,rp);form.Apply(minus,rm)
        finite_difference=(rp.FV().NumPy()-rm.FV().NumPy())/.02
        expected=jacobian.FV().NumPy()
        self.assertLess(np.linalg.norm((finite_difference-expected)[free])/np.linalg.norm(expected[free]),1e-5)
