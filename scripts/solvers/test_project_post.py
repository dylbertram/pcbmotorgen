import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from post_project_force import completed_field


class ProjectPostTest(unittest.TestCase):
    def test_failure_receipt_or_changed_fields_prevent_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);job=work/'bare';job.mkdir()
            field=job/'air.pos';field.write_text('raw air')
            pro=job/'project.pro';pro.write_text('original formulation')
            mesh=work/'project.msh';mesh.write_text('original physical mesh')
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            source={'status':'comparison-only','failures':[],'mesh_sha256':digest(mesh),
                    'runs':{'bare':{'air_field_sha256':digest(field),'formulation_sha256':digest(pro)}}}
            (work/'summary.json').write_text(json.dumps(source))
            receipt=job/'solve.log.command.json'
            receipt.write_text(json.dumps({'status':'timeout'}))
            with self.assertRaises(ValueError):completed_field(work,'bare')
            receipt.write_text(json.dumps({'status':'completed','exit_code':0}))
            self.assertEqual(completed_field(work,'bare')[1],field)
            for status in ['running','failed','mesh-only']:
                source['status']=status;(work/'summary.json').write_text(json.dumps(source))
                with self.assertRaises(ValueError):completed_field(work,'bare')
            source['status']='completed-bare-field-only-unqualified'
            (work/'summary.json').write_text(json.dumps(source))
            self.assertEqual(completed_field(work,'bare')[1],field)
            with self.assertRaises(ValueError):completed_field(work,'stack')
            mesh.write_text('changed mesh')
            with self.assertRaises(ValueError):completed_field(work,'bare')
            mesh.write_text('original physical mesh')
            field.write_text('changed output')
            with self.assertRaises(ValueError):completed_field(work,'bare')


if __name__=='__main__':
    unittest.main()
