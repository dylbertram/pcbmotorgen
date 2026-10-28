import importlib.util
import unittest

import numpy as np

from ngsolve_material_motion import magnetic_form,midpoint_arrays
from vector_material import magnetization_b


class MidpointArrayTest(unittest.TestCase):
    def test_static_nonzero_bias_has_exactly_zero_time_derivative(self):
        previous=np.array([1.234567891234e-7,-9.876543219876e-8,0.])
        following,derivative=midpoint_arrays(previous.copy(),previous,2,.00025)
        np.testing.assert_array_equal(following,previous)
        np.testing.assert_array_equal(derivative,0.)

    def test_current_uses_the_midpoint_difference_before_endpoint_rounding(self):
        previous=np.array([.1,-.2,0.]);midpoint=np.array([.10001,-.19999,3.])
        following,derivative=midpoint_arrays(midpoint,previous,2,.001)
        np.testing.assert_allclose(derivative[:2],2*(midpoint[:2]-previous[:2])/.001)
        np.testing.assert_allclose(following[:2],2*midpoint[:2]-previous[:2])
        self.assertEqual(following[2],0.);self.assertEqual(derivative[2],0.)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class MaterialMotionEnergyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        cls.ng=ng;body=Box(Pnt(0,0,0),Pnt(.003,.003,.001));body.mat('fer');body.faces.name='outer'
        cls.mesh=ng.Mesh(OCCGeometry(body).GenerateMesh(maxh=.002))
        cls.model={'stack':[{'name':'fer','mu_r':130.,'bsat_t':.25}]}
        cls.rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,8)}

    def test_compound_energy_uses_vector_A_and_not_the_potential_component(self):
        ng=self.ng;a=ng.HCurl(self.mesh,order=0,nograds=True);p=ng.H1(self.mesh,order=1);compound=a*p
        source=ng.CoefficientFunction((.1,.2,.3))
        single=magnetic_form(ng,a,self.mesh,self.model,source,self.rules)
        combined=magnetic_form(ng,compound,self.mesh,self.model,source,self.rules)
        x=ng.GridFunction(a);y=ng.GridFunction(compound)
        x.vec.FV().NumPy()[:]=np.linspace(0.,1e-8,a.ndof)
        y.vec.FV().NumPy()[:a.ndof]=x.vec.FV().NumPy();y.vec.FV().NumPy()[a.ndof:]=.1
        self.assertAlmostEqual(float(single.Energy(x.vec)),float(combined.Energy(y.vec)),places=13)

    def test_source_derivative_is_the_material_interaction_work_term(self):
        ng=self.ng;a=ng.HCurl(self.mesh,order=0,nograds=True);state=ng.GridFunction(a)
        position=ng.Parameter(0.);source=ng.CoefficientFunction((.2,.1,.3+position))
        form=magnetic_form(ng,a,self.mesh,self.model,source,self.rules)
        delta=1e-6;position.Set(delta);above=float(form.Energy(state.vec));position.Set(-delta);below=float(form.Energy(state.vec));position.Set(0.)
        moment=magnetization_b(ng,source,130.,.25)
        expected=float(ng.Integrate(-ng.InnerProduct(moment,source.Diff(position)),self.mesh,order=8))
        self.assertAlmostEqual(((above-below)/(2*delta))/expected,1.,places=8)
