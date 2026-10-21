import importlib.util
import copy
import unittest

import numpy as np

from audit_finite_dc_sections import section,tetrahedra
from finite_copper_curvature import generate_mesh,validate_mesh_reuse


class CurvatureInputTest(unittest.TestCase):
    def test_invalid_or_unrefined_controls_rejected(self):
        for size,safety in [(-1,4),(.0002,2),(.0002,float('nan'))]:
            with self.assertRaises(ValueError):generate_mesh(None,None,size,safety)

    def test_reuse_requires_identical_inputs_and_preassembly_resource_failure(self):
        source={'version':'pinned','input_hashes':{'saved':'hash'},'geometry':{'volume':1.},'brep_sha256':'cad',
            'request':{'mesh_m':.00015,'port_fraction':.5,'geometry_order':1,'iterative':True}}
        prior=copy.deepcopy(source);prior.update(status='failed',error='Curvature DC resource cap exceeded before assembly')
        prior['request']['curvature_safety']=4.
        validate_mesh_reuse(prior,source,4.)
        for key,value in [('status','running'),('error','nonlinear failure'),('brep_sha256','changed')]:
            changed=copy.deepcopy(prior);changed[key]=value
            with self.assertRaises(ValueError):validate_mesh_reuse(changed,source,4.)
        with self.assertRaises(ValueError):validate_mesh_reuse(prior,source,3.)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve required')
class CurvatureGeometryTest(unittest.TestCase):
    def test_saved_radius_and_plating_barrel_section(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir
        inner=.00015;outer=.000175;height=.0008
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        mesh=generate_mesh(ng,ring,.00015,4.)
        value=section(mesh,ng.CoefficientFunction((0,0,1)),tetrahedra(mesh),[0,0,.000371],[0,0,1],outer*1.2)
        self.assertLess(abs(value['area_m2']/(np.pi*(outer**2-inner**2))-1),.02)
