import copy
import json
from pathlib import Path
import tempfile
import unittest

from audit_dc_mesh_section_areas import area_check,checkpoint_inputs
from post_project_force import sha


class MeshAreaGateTest(unittest.TestCase):
    def test_finite_barrel_area_measured_without_a_current_solution(self):
        import numpy as np
        import ngsolve as ng
        from netgen.occ import Cylinder,Pnt,Dir,OCCGeometry
        from audit_finite_dc_sections import section,tetrahedra
        inner=.00015;outer=.000175;height=.001
        barrel=Cylinder(Pnt(0,0,0),Dir(0,0,1),outer,height)-Cylinder(Pnt(0,0,0),Dir(0,0,1),inner,height)
        mesh=ng.Mesh(OCCGeometry(barrel).GenerateMesh(maxh=.0003,curvaturesafety=4));mesh.Curve(1)
        value=section(mesh,ng.CoefficientFunction((0.,0.,0.)),tetrahedra(mesh),[0.,0.,height/2],[0.,0.,1.],outer*1.2)
        self.assertEqual(value['current_a'],0.)
        self.assertTrue(area_check(value['area_m2'],np.pi*(outer**2-inner**2))['passed'])

    def test_original_area_gate_not_relaxed(self):
        self.assertTrue(area_check(1.019,1.)['passed'])
        self.assertFalse(area_check(.979,1.)['passed'])
        for area,expected in [(0.,1.),(1.,0.),(float('nan'),1.),(-1.,1.)]:
            with self.subTest(area=area,expected=expected),self.assertRaises(ValueError):area_check(area,expected)

    def test_only_finished_immutable_input_checkpoint_without_fields(self):
        source=dict(version='pinned',input_hashes={},geometry={},brep_sha256='',
            request=dict(mesh_m=.0004,port_fraction=.5,geometry_order=1,iterative=True))
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);(work/'mesh.vol').write_bytes(b'exact-mesh-fixture');(work/'closed-copper.brep').write_bytes(b'cad')
            source['brep_sha256']=sha(work/'closed-copper.brep')
            implementation=work/'archived.py';implementation.write_text('fixture\n')
            receipt=work/'receipt.json';receipt.write_text(json.dumps(dict(status='completed',exit_code=0)))
            report=copy.deepcopy(source);report.update(status='completed-finite-copper-curvature-mesh-only',
                mesh_sha256=sha(work/'mesh.vol'),command_receipt=str(receipt),
                source_snapshots={'implementation':dict(snapshot='archived.py',sha256=sha(implementation))})
            report['request']['curvature_safety']=4.
            def save():(work/'summary.json').write_text(json.dumps(report))
            save();self.assertEqual(checkpoint_inputs(work,source)['mesh_sha256'],report['mesh_sha256'])
            (work/'dc-current-potential.sol').write_bytes(b'not-an-input-checkpoint')
            with self.assertRaisesRegex(ValueError,'must not import'):checkpoint_inputs(work,source)
            (work/'dc-current-potential.sol').unlink()
            receipt.write_text(json.dumps(dict(status='running',exit_code=None)))
            with self.assertRaisesRegex(ValueError,'finished whole-job'):checkpoint_inputs(work,source)
            receipt.write_text(json.dumps(dict(status='completed',exit_code=0)))
            (work/'mesh.vol').write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'bytes changed'):checkpoint_inputs(work,source)
