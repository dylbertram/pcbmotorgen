import importlib.util
import copy
import unittest

import numpy as np

from audit_finite_dc_sections import section,tetrahedra
from finite_copper_curvature import generate_mesh,validate_mesh_reuse,mesh_retained_cad


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
        checkpoint=copy.deepcopy(prior);checkpoint['status']='completed-finite-copper-curvature-mesh-only';checkpoint.pop('error')
        validate_mesh_reuse(checkpoint,source,4.)


@unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve required')
class CurvatureGeometryTest(unittest.TestCase):
    def test_retained_cad_reuse_is_byte_bound_and_preserves_drive_partition(self):
        import tempfile
        from pathlib import Path
        import ngsolve as ng
        from netgen.occ import Box,Pnt,Glue,OCCGeometry
        from post_project_force import sha
        copper=Box(Pnt(0,0,0),Pnt(.8,1,1));copper.mat('copper')
        drive=Box(Pnt(.8,0,0),Pnt(1,1,1));drive.mat('drive')
        initial=ng.Mesh(OCCGeometry(Glue([copper,drive])).GenerateMesh(maxh=.4));initial.Curve(1)
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);initial.ngmesh.Save(str(work/'mesh.vol'))
            source=dict(version=ng.__version__,mesh_sha256=sha(work/'mesh.vol'),request=dict(mesh_m=.4),
                geometry=dict(volume_m3=1.,drive_volume_m3=.2,drive_path_m=[[.8,.5,.5],[1.,.5,.5]]))
            stages=[]
            result,identity=mesh_retained_cad(ng,work,source,4.,lambda stage,**kw:stages.append(stage))
            self.assertEqual(set(result.GetMaterials()),{'copper','drive'})
            self.assertLess(identity['cad_volume_relative_reload_error'],1e-9)
            self.assertIn('native-mesh-generation-complete',stages)
            changed=copy.deepcopy(source);changed['mesh_sha256']='same-counts-are-not-identity'
            with self.assertRaisesRegex(ValueError,'immutable original mesh'):
                mesh_retained_cad(ng,work,changed,4.)
            changed=copy.deepcopy(source);changed['geometry']['drive_volume_m3']=.1
            with self.assertRaisesRegex(ValueError,'drive identity'):
                mesh_retained_cad(ng,work,changed,4.)
            changed=copy.deepcopy(source);changed['geometry']['drive_path_m']=[[.7,.5,.5],[.9,.5,.5]]
            with self.assertRaisesRegex(ValueError,'drive identity'):
                mesh_retained_cad(ng,work,changed,4.)

    def test_saved_radius_and_plating_barrel_section(self):
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir
        inner=.00015;outer=.000175;height=.0008
        ring=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        mesh=generate_mesh(ng,ring,.00015,4.)
        value=section(mesh,ng.CoefficientFunction((0,0,1)),tetrahedra(mesh),[0,0,.000371],[0,0,1],outer*1.2)
        self.assertLess(abs(value['area_m2']/(np.pi*(outer**2-inner**2))-1),.02)
