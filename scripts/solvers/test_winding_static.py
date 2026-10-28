import importlib.util
import unittest

import numpy as np

from closed_wire_source import coefficient
from ngsolve_material_motion import magnetic_form
from ngsolve_winding_static import line_samples,current_difference_entry
from vector_material import magnetization_b


class WireQuadratureTest(unittest.TestCase):
    def test_unresolved_interface_source_never_emits_a_physical_inductance(self):
        result=current_difference_entry(.05,[.1,0.,0.],1.3e-7,False)
        self.assertIsNone(result['material_differential_line_inductance_h'])
        self.assertEqual(result['unqualified_material_current_difference_h'],1.3e-7)
        self.assertEqual(result['mover_kf_n_per_a'],[.1,0.,0.])

    def test_signed_line_elements_and_depth_are_preserved(self):
        segments=np.array([[[0.,0.,0.],[0.,0.,.0008]],[[.001,0.,.0008],[.002,0.,.0008]]])
        currents=np.array([1.,-.5]);points,dl=line_samples(segments,currents,20)
        np.testing.assert_allclose(dl.reshape(2,20,3).sum(axis=1),currents[:,None]*(segments[:,1]-segments[:,0]))
        self.assertTrue(np.all(points[:20,2]>0.));self.assertTrue(np.all(points[:20,2]<.0008))


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
class WindingMaterialEnergyTest(unittest.TestCase):
    def test_material_linkage_is_negative_partial_current_energy_derivative(self):
        import ngsolve as ng
        from netgen.occ import Box,Pnt,OCCGeometry
        body=Box(Pnt(-.001,-.001,-.001),Pnt(.001,.001,-.0002));body.mat('fer');body.faces.name='outer'
        mesh=ng.Mesh(OCCGeometry(body).GenerateMesh(maxh=.001))
        path=np.array([[-.003,-.003,.001],[.003,-.003,.001],[.003,.003,.001],[-.003,.003,.001],[-.003,-.003,.001]])
        segments=np.stack([path[:-1],path[1:]],axis=1);wire,_=coefficient(ng,segments,np.ones(4))
        amplitude=ng.Parameter(.1);space=ng.HCurl(mesh,order=0,nograds=True);state=ng.GridFunction(space)
        model={'stack':[{'name':'fer','mu_r':130.,'bsat_t':.25}]};rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,8)}
        for strength in [.001,.3]:
            source=ng.CoefficientFunction((0.,0.,strength))+amplitude*wire
            form=magnetic_form(ng,space,mesh,model,ng.CacheCF(source),rules)
            moment=magnetization_b(ng,source,130.,.25);linkage=float(ng.Integrate(ng.InnerProduct(moment,wire),mesh,order=8))
            delta=1e-3;amplitude.Set(.1+delta);above=float(form.Energy(state.vec));amplitude.Set(.1-delta);below=float(form.Energy(state.vec));amplitude.Set(.1)
            derivative=(above-below)/(2*delta)
            self.assertAlmostEqual(derivative/(-linkage),1.,places=7)
