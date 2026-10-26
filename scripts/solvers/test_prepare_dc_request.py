"""Preparation handoff contracts with mocked CAD, not numerical evidence."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import prepare_dc_request as preparation


class GeometryHandoffTest(unittest.TestCase):
    def test_mocked_whole_pipeline_preserves_request_digest_through_publication(self):
        # All CAD/current/audit/export operations are mocked. This covers final
        # orchestration, not numerical acceptance or reuse of failed artifacts.
        with TemporaryDirectory() as folder:
            root=Path(folder).resolve();request=root/'request.json';request.write_text('{"request_id":"whole-contract"}')
            bound=root/'study-binding.json';bound.write_text('a different digest')
            work=root/'result';hashes={}
            class Evidence:
                def __init__(self):self.hashes=hashes
                def digest(self,path):
                    value=preparation.sha(Path(path));self.hashes[str(path)]=value;return value
                def report(self,path,flag):self.digest(path)
                def unchanged(self):pass
            def run(command,where,log,**kwargs):
                for name in ['geometry/summary.json','source/summary.json','active.json','passive.json','return.json',
                             'independent/summary.json','rt0/summary.json','source/dc-current-potential.sol','independent/potential.sol','rt0/rt0-source.npz']:
                    path=work/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text(json.dumps(dict(geometry=dict(copper_resistivity_ohm_m=1.7e-8))))
                return .01
            def load(*args):return dict(study_bindings={str(bound):preparation.sha(bound)})
            with patch('sys.argv',['prepare_dc_request.py','--request',str(request),'--work',str(work)]), \
                 patch.object(preparation,'problems',return_value=[]),patch.object(preparation,'actual_inputs',return_value={}), \
                 patch.object(preparation,'run',side_effect=run),patch.object(preparation,'load',side_effect=load), \
                 patch.object(preparation,'Evidence',Evidence),patch.object(preparation,'resistance_check',return_value=dict(passed=True)):
                preparation.main()
            report=json.loads((work/'summary.json').read_text())
            self.assertEqual(report['input_request_sha256'],preparation.sha(request))
            self.assertEqual(report['status'],'prepared-request-bound-current-source-not-qualified')
            self.assertEqual(report['force_status'],'unqualified')
            self.assertTrue(all(s['state']=='completed' for s in report['stages'].values()))

    def test_failed_stage_cannot_leave_running_progress_in_final_report(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=root/'request.json';request.write_text('{"request_id":"failed-stage"}\n')
            def run(command,work,log,**kwargs):
                if log=='geometry.log':return .1
                raise RuntimeError('Deliberate source-stage failure, no numerical job launched')
            with patch('sys.argv',['prepare_dc_request.py','--request',str(request),'--work',str(root/'result')]), \
                 patch.object(preparation,'problems',return_value=[]), \
                 patch.object(preparation,'actual_inputs',return_value={}), \
                 patch.object(preparation,'run',side_effect=run), \
                 self.assertRaisesRegex(RuntimeError,'Deliberate source-stage failure'):
                preparation.main()
            report=json.loads((root/'result/summary.json').read_text())
            self.assertEqual(report['status'],'failed-request-bound-current-preparation')
            self.assertEqual(report['source_status'],'failed')
            self.assertEqual(report['force_status'],'unqualified')
            self.assertEqual(report['stages']['geometry']['state'],'completed')
            self.assertEqual(report['stages']['source']['state'],'failed')
            self.assertIn('Deliberate source-stage failure',report['stages']['source']['error'])
            self.assertFalse(any(stage['state']=='running' for stage in report['stages'].values()))

    def test_return_report_survives_implementation_hash_iteration(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=root/'request.json';request.write_text('{"request_id":"handoff"}\n')
            actual=dict(snapshot=dict(routing=dict(vias=[],segments=[dict(layer=0)])),
                translation_m=[0.,0.,0.],closure=dict(return_path_m=[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]]),
                model=dict(test_only=True),return_width_m=.001,return_thickness_m=.000035)
            def brep(path):Path(path).write_bytes(b'mocked CAD serialization, not geometry evidence')
            copper=SimpleNamespace(mass=1.,WriteBrep=brep)
            with patch.dict('os.environ',{'PCB_MOTOR_COMMAND_RECEIPT':str(root/'receipt.json')}), \
                 patch.object(preparation,'actual_inputs',return_value=deepcopy(actual)), \
                 patch.object(preparation,'build',return_value=(copper,{})), \
                 patch.object(preparation,'validate_copper_shape'), \
                 patch.object(preparation,'union_gate',return_value=dict(passed=True)), \
                 patch.object(preparation,'closed_return',return_value=(copper,dict(passed=True))), \
                 patch.object(preparation,'partition_checks',return_value=dict(passed=True)):
                preparation.geometry(request,root/'geometry')
            geometry=json.loads((root/'geometry/summary.json').read_text())
            returned=json.loads((root/'geometry/return/summary.json').read_text())
            self.assertEqual(geometry['status'],'completed-finite-copper-geometry-only-unqualified')
            self.assertEqual(returned['status'],'prepared-physical-dc-return-geometry-only')
            self.assertEqual(returned['closure'],actual['closure'])
            self.assertEqual(returned['translation_m'],actual['translation_m'])
            self.assertEqual(returned['failures'],[])
            self.assertEqual(returned['input_hashes'],geometry['input_hashes'])
            self.assertEqual(returned['command_receipt'],str(root/'receipt.json'))
            self.assertTrue(returned['source_snapshots'])
            self.assertNotIn('sha256',returned)


if __name__=='__main__':unittest.main()
