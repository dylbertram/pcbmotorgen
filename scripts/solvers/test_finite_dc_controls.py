import copy
import json
from pathlib import Path
import tempfile
import unittest

from audit_finite_dc_controls import MIXED,validate_control,validate_dc,resistance_check,load
from post_project_force import sha


def report():
    return {'status':MIXED,'version':'pinned','input_hashes':{'saved':'hash'},
        'request':{'mesh_m':.0002,'port_fraction':.5,'geometry_order':1,'iterative':True},
        'geometry':{'volume_m3':1.,'solid_components':1,'return_path_m':[[0,0,0],[1,0,0]],
            'return_width_m':.0002,'return_thickness_m':35e-6,'drive_path_m':[[.2,0,0],[.8,0,0]]},
        'mesh_sha256':'coarse','mesh_elements':100,'geometric_volume_check':{'mesh_volume_m3':.999},
        'dc':{'relative_equation_residual':1e-13,'relative_power_balance':1e-13,
            'net_current_relative_error':1e-15,'source_power_w':.2,'joule_power_w':.2,'effective_loop_resistance_ohm':5.}}


class FiniteDCControlsTest(unittest.TestCase):
    def test_isolated_mesh_refinement(self):
        a=report();b=copy.deepcopy(a);b['request']['mesh_m']=.00015;b['mesh_sha256']='fine';b['mesh_elements']=150
        validate_control(a,b,'mesh')
        b['request']['port_fraction']=.4
        with self.assertRaisesRegex(ValueError,'isolated'):validate_control(a,b,'mesh')

    def test_port_control_preserves_copper(self):
        a=report();b=copy.deepcopy(a);b['request']['port_fraction']=.4
        b['geometry']['drive_path_m']=[[.3,0,0],[.7,0,0]]
        validate_control(a,b,'port')
        b['geometry']['return_width_m']=.0003
        with self.assertRaisesRegex(ValueError,'copper/return'):validate_control(a,b,'port')

    def test_partial_failed_and_nonfinite_are_rejected(self):
        for status in ['running','failed']:
            a=report();a['status']=status
            with self.assertRaises(ValueError):validate_dc(a,MIXED)
        for key in report()['dc']:
            a=report();a['dc'][key]=float('nan')
            with self.assertRaises(ValueError):validate_dc(a,MIXED)

    def test_original_gates_and_unit_drive_are_not_relaxed(self):
        for key,value in [('relative_equation_residual',2e-9),('relative_power_balance',2e-8),
                ('net_current_relative_error',2e-9),('source_power_w',.3),('effective_loop_resistance_ohm',6.)]:
            a=report();a['dc'][key]=value
            with self.assertRaises(ValueError):validate_dc(a,MIXED)

    def test_same_mesh_or_curved_geometry_does_not_pass_refinement(self):
        a=report();b=copy.deepcopy(a);b['request']['mesh_m']=.00015
        with self.assertRaisesRegex(ValueError,'finer'):validate_control(a,b,'mesh')
        a['request']['geometry_order']=2;b['request']['geometry_order']=2
        with self.assertRaisesRegex(ValueError,'Curved'):validate_control(a,b,'mesh')

    def test_resistance_failure_is_retained(self):
        a=report();b=report();b['dc']['effective_loop_resistance_ohm']=5.2
        self.assertFalse(resistance_check(a,b,.02)['passed'])
        self.assertTrue(resistance_check(a,b,.05)['passed'])

    def test_receipt_input_and_archived_implementation_must_match(self):
        for changed in [None,'receipt','mesh.vol','saved-input.json','implementation.py','escape']:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as folder:
                work=Path(folder);a=report()
                for name in ['mesh.vol','closed-copper.brep','dc-current-potential.sol','saved-input.json','implementation.py']:
                    (work/name).write_text('original')
                receipt=work/'receipt.json';receipt.write_text(json.dumps({'status':'completed','exit_code':0}))
                a.update(command_receipt=str(receipt),mesh_sha256=sha(work/'mesh.vol'),
                    solution_sha256=sha(work/'dc-current-potential.sol'),brep_sha256=sha(work/'closed-copper.brep'),
                    input_hashes={str(work/'saved-input.json'):sha(work/'saved-input.json')},
                    source_snapshots={'implementation':{'snapshot':'implementation.py','sha256':sha(work/'implementation.py')}})
                if changed=='receipt':receipt.write_text(json.dumps({'status':'running','exit_code':None}))
                elif changed=='escape':a['source_snapshots']['implementation']['snapshot']='../implementation.py'
                elif changed:(work/changed).write_text('changed')
                (work/'summary.json').write_text(json.dumps(a))
                if changed:
                    with self.assertRaises(ValueError):load(work,MIXED)
                else:self.assertEqual(load(work,MIXED)['status'],MIXED)
