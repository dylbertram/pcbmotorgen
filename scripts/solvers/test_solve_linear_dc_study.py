import copy
import json
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

import solve_linear_dc_study as source
from solve_linear_dc_study import validate_controls,validate_source_inputs
from post_project_force import sha


class LinearSourceControlsTest(unittest.TestCase):
    def setUp(self):
        self.matrix=json.loads((Path(__file__).parent/'cases/linear-dc-day-acceptance-matrix-20261022.json').read_text())
        self.study=dict(status='prepared-actual-linear-study-no-source-or-force-acceptance')

    def test_declared_curvature4_and6_are_explicit(self):
        for curvature in [4.,6.]:validate_controls(self.matrix,self.study,.0002,curvature,.5,24000000)

    def test_no_implicit_default_or_undeclared_controls(self):
        for mesh,curvature,port,cap in [(.0002,2.,.5,24000000),(.0003,4.,.5,24000000),(.0002,4.,.3,24000000),(.0002,4.,.5,24000001),(.0002,4.,.5,True)]:
            with self.assertRaises(ValueError):validate_controls(self.matrix,self.study,mesh,curvature,port,cap)
        study=copy.deepcopy(self.study);study['status']='running'
        with self.assertRaises(ValueError):validate_controls(self.matrix,study,.0002,4.,.5,24000000)


class SourceHandoffTest(unittest.TestCase):
    """Small contract fixtures only, not geometry or numerical acceptance."""
    def fixture(self,root):
        root=root.resolve()
        origin=root/'geometry';(origin/'return').mkdir(parents=True);(origin/'study').mkdir()
        request=root/'request.json';request.write_text('{}')
        fixture=origin/'study/fixture.json';fixture.write_text('{}')
        receipt=root/'receipt.json';receipt.write_text(json.dumps(dict(status='completed',exit_code=0)))
        study=origin/'study/summary.json';study.write_text(json.dumps(dict(status='prepared-actual-linear-study-no-source-or-force-acceptance',input_hashes={str(request):sha(request)})))
        for name in ['copper.brep','closed-copper-for-partition-audit.brep']:(origin/name).write_text('mocked CAD, not numerical evidence')
        hashes={str(request):sha(request),str(fixture):sha(fixture),str(study):sha(study)}
        physical=dict(status='completed-finite-copper-geometry-only-unqualified',failures=[],command_receipt=str(receipt),
            actual_study_work=str(study.parent),translation_m=[0.,0.,0.],input_hashes=hashes,
            geometry=dict(layers=[dict(trace_width_m=.001,thickness_m=.000035)],copper_resistivity_ohm_m=1.7e-8),
            closed_partition_volume_m3=1e-8,brep_sha256=sha(origin/'copper.brep'),closed_partition_brep_sha256=sha(origin/'closed-copper-for-partition-audit.brep'))
        returned=dict(status='prepared-physical-dc-return-geometry-only',failures=[],command_receipt=str(receipt),
            translation_m=[0.,0.,0.],input_hashes=hashes,closure=dict(return_path_m=[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]]))
        (origin/'summary.json').write_text(json.dumps(physical));(origin/'return/summary.json').write_text(json.dumps(returned))
        matrix=root/'matrix.json';matrix.write_text(json.dumps(dict(schema='declared-linear-dc-acceptance-matrix-v1',study_inputs=str(request),
            source_controls=dict(mesh_m=[.0002],curvature_safety=[6.],port_fraction=[.5]))))
        return origin,matrix

    def test_valid_handoff_is_bound_and_not_mutated(self):
        with TemporaryDirectory() as folder:
            origin,matrix=self.fixture(Path(folder));_,_,_,hashes=validate_source_inputs(origin,matrix,.0002,6.,.5,24000000)
            self.assertGreaterEqual(len(hashes),8)
            for path,digest in hashes.items():self.assertEqual(sha(Path(path)),digest)

    def test_corrupt_reports_receipts_and_inputs_are_rejected(self):
        for change in ['overwritten-return','missing-receipt','failed-receipt','bool-exit','changed-request','changed-cad','closure','provenance','failure','controls','list-report','nan-return','zero-drive','invalid-study','bool-width','conflicting-hash']:
            with self.subTest(change=change),TemporaryDirectory() as folder:
                root=Path(folder).resolve();origin,matrix=self.fixture(root)
                validate_source_inputs(origin,matrix,.0002,6.,.5,24000000)
                path=origin/'return/summary.json';value=json.loads(path.read_text())
                if change=='overwritten-return':value={'sha256':'metadata-not-a-return-report'}
                elif change=='missing-receipt':value.pop('command_receipt')
                elif change=='failed-receipt':(root/'receipt.json').write_text('{"status":"failed","exit_code":1}')
                elif change=='bool-exit':(root/'receipt.json').write_text('{"status":"completed","exit_code":false}')
                elif change=='changed-request':(root/'request.json').write_text('{"changed":true}')
                elif change=='changed-cad':(origin/'copper.brep').write_text('changed')
                elif change=='closure':value['closure']={}
                elif change=='provenance':value['translation_m']=[1.,0.,0.]
                elif change=='failure':value['failures']=['failed']
                elif change=='controls':matrix.write_text('{"schema":"wrong"}')
                elif change=='list-report':value=[]
                elif change=='nan-return':value['closure']['return_path_m'][1][0]=float('nan')
                elif change=='zero-drive':value['closure']['return_path_m'][2]=value['closure']['return_path_m'][1]
                elif change=='invalid-study':
                    (origin/'study/summary.json').write_text('{"status":"prepared-actual-linear-study-no-source-or-force-acceptance","input_hashes":[]}')
                elif change=='bool-width':
                    physical=json.loads((origin/'summary.json').read_text());physical['geometry']['layers'][0]['trace_width_m']=True
                    (origin/'summary.json').write_text(json.dumps(physical))
                else:
                    physical=json.loads((origin/'summary.json').read_text())
                    physical['input_hashes'][str(root/'request.json')]='stale-copper-binding'
                    value['input_hashes']=copy.deepcopy(physical['input_hashes'])
                    (origin/'summary.json').write_text(json.dumps(physical))
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):validate_source_inputs(origin,matrix,.0002,6.,.5,24000000)

    def test_validate_only_never_calls_mesh_or_solve_and_preserves_outputs(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);origin,matrix=self.fixture(root);work=root/'validation'
            argv=['solve_linear_dc_study.py','--geometry-work',str(origin),'--matrix',str(matrix),'--work',str(work),
                '--mesh','.0002','--curvature-safety','6','--port-fraction','.5','--max-dofs','24000000','--validate-only']
            with patch('sys.argv',argv),patch.object(source,'mesh_cad') as mesh,patch.object(source,'solve') as solve:
                source.main();mesh.assert_not_called();solve.assert_not_called()
                report=json.loads((work/'summary.json').read_text());self.assertFalse(report['mesh_or_solve_performed'])
                self.assertEqual(report['source_status'],'unqualified');self.assertEqual(report['force_status'],'unqualified')
                from dc_preparation import validate_prepared_summary
                with self.assertRaises(ValueError):validate_prepared_summary(report,'not-a-prepared-source')
                before=(work/'summary.json').read_bytes()
                with self.assertRaises(SystemExit):source.main()
                self.assertEqual((work/'summary.json').read_bytes(),before)

    def test_validation_only_cannot_request_numerical_modes(self):
        for extra in [['--mesh-only'],['--mesh-work','/not-a-checkpoint']]:
            with self.subTest(extra=extra),TemporaryDirectory() as folder:
                root=Path(folder);origin,matrix=self.fixture(root);work=root/'validation'
                argv=['solve_linear_dc_study.py','--geometry-work',str(origin),'--matrix',str(matrix),'--work',str(work),
                    '--mesh','.0002','--curvature-safety','6','--port-fraction','.5','--max-dofs','24000000','--validate-only',*extra]
                with patch('sys.argv',argv),patch.object(source,'validate_source_inputs') as validate,self.assertRaises(SystemExit):source.main()
                validate.assert_not_called();self.assertFalse(work.exists())
