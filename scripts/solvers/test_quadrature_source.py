import importlib.util
import unittest

import numpy as np

from quadrature_source import fixed_source,update_source
from ngsolve_material_motion import magnetic_form


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class QuadratureSourceTest(unittest.TestCase):
    def test_probe_order_mismatch_is_rejected_before_native_field_evaluation(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        body=Box(Pnt(0,0,0),Pnt(.003,.002,.001));body.mat('fer')
        mesh=ng.Mesh(OCCGeometry(body).GenerateMesh(maxh=.002))
        source=ng.CoefficientFunction((ng.x,ng.y,ng.z))
        cached,storage,rules,_=fixed_source(ng,mesh,source,'fer',8)
        self.assertEqual(cached.dim,3)
        self.assertTrue(all(component.dim==1 for component in storage))
        class MustNotEvaluate:
            dim=3
            def __call__(self,*args):raise AssertionError('Unsafe rule reached native field evaluation')
        # The reported probe used IR-space order4 but integration degree4.
        # Supported scalar storage here has the matching degree8 rule. Reject
        # the old mismatch in Python; do not reproduce the native vector crash.
        wrong={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,4)}
        with self.assertRaisesRegex(ValueError,'exact stored/assembled'):
            update_source(ng,mesh,MustNotEvaluate(),storage,wrong,'fer',8)

    def test_source_update_changes_an_existing_nonlinear_form_without_freezing_material(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        body=Box(Pnt(0,0,0),Pnt(.003,.002,.001));body.mat('fer');body.faces.name='outer'
        mesh=ng.Mesh(OCCGeometry(body).GenerateMesh(maxh=.002));space=ng.HCurl(mesh,order=0,nograds=True);state=ng.GridFunction(space)
        parameter=ng.Parameter(0.);source=ng.CoefficientFunction((.1*ng.exp(100*ng.x),.2+ng.y,.3+parameter+ng.z)).Compile()
        cached,storage,rules,_=fixed_source(ng,mesh,source,'fer',6)
        model={'stack':[{'name':'fer','mu_r':130.,'bsat_t':.25}]}
        direct=magnetic_form(ng,space,mesh,model,source,rules);fast=magnetic_form(ng,space,mesh,model,cached,rules)
        before=float(fast.Energy(state.vec));parameter.Set(-.2)
        proof=update_source(ng,mesh,source,storage,rules,'fer',6)
        self.assertLess(proof['relative_source_l2_error'],1e-14)
        self.assertNotAlmostEqual(before,float(fast.Energy(state.vec)),places=10)
        self.assertAlmostEqual(float(direct.Energy(state.vec)),float(fast.Energy(state.vec)),places=13)
        direct.AssembleLinearization(state.vec);fast.AssembleLinearization(state.vec)
        direction=state.vec.CreateVector();direction.FV().NumPy()[:]=.1
        a=state.vec.CreateVector();b=state.vec.CreateVector();a.data=direct.mat*direction;b.data=fast.mat*direction
        np.testing.assert_allclose(a.FV().NumPy(),b.FV().NumPy(),rtol=1e-12,atol=1e-9)

    def test_exact_source_cache_preserves_energy_gradient_and_full_material_tangent(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        body=Box(Pnt(0,0,0),Pnt(.003,.002,.001));body.mat('fer');body.faces.name='outer'
        mesh=ng.Mesh(OCCGeometry(body).GenerateMesh(maxh=.002));space=ng.HCurl(mesh,order=0,nograds=True)
        source=ng.CoefficientFunction((ng.exp(100*ng.x)*.1,.2+ng.y,.3+ng.z)).Compile();degree=6
        cached,storage,rules,metadata=fixed_source(ng,mesh,source,'fer',degree)
        self.assertLess(metadata['relative_source_l2_error'],1e-14)
        model={'stack':[{'name':'fer','mu_r':130.,'bsat_t':.25}]}
        direct=magnetic_form(ng,space,mesh,model,source,rules);fast=magnetic_form(ng,space,mesh,model,cached,rules)
        state=ng.GridFunction(space);state.vec.FV().NumPy()[:]=np.linspace(0.,1e-8,space.ndof)
        self.assertAlmostEqual(float(direct.Energy(state.vec)),float(fast.Energy(state.vec)),places=13)
        a=state.vec.CreateVector();b=state.vec.CreateVector();direct.Apply(state.vec,a);fast.Apply(state.vec,b)
        np.testing.assert_allclose(a.FV().NumPy(),b.FV().NumPy(),rtol=1e-12,atol=1e-12)
        direct.AssembleLinearization(state.vec);fast.AssembleLinearization(state.vec)
        direction=state.vec.CreateVector();direction.FV().NumPy()[:]=np.linspace(.1,.2,space.ndof)
        a.data=direct.mat*direction;b.data=fast.mat*direction
        np.testing.assert_allclose(a.FV().NumPy(),b.FV().NumPy(),rtol=1e-12,atol=1e-9)

    def test_odd_or_nonpositive_rule_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'even integration'):fixed_source(None,None,None,'fer',3)
