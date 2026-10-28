import json
import copy
import tempfile
import unittest
from pathlib import Path

from post_project_force import sha
from post_reduced_force import case_field, quadrature_levels, force_level_checks


class ReducedForceReceiptTest(unittest.TestCase):
    def test_independent_evaluator_keeps_the_original_floor_balance_and_quadrature_gates(self):
        paths=['0.0001','0.0002','0.0003']
        def body(z):return {c:{'force_n':[0,0,z]} for c in paths}
        level={'bare':{'stator':body(0),'mover':body(0)},'stack':{'stator':body(1),'mover':body(-1)}}
        levels={'1':copy.deepcopy(level),'2':copy.deepcopy(level)}
        self.assertEqual(force_level_checks(levels,[1,2]),[])
        changed=copy.deepcopy(levels);changed['1']['stack']['stator']=body(1.05);changed['1']['stack']['mover']=body(-1.05)
        self.assertTrue(any('quadrature' in error for error in force_level_checks(changed,[1,2])))
        changed=copy.deepcopy(levels);changed['2']['bare']['mover']=body(.03)
        self.assertTrue(any('floor' in error for error in force_level_checks(changed,[1,2])))
        changed=copy.deepcopy(levels);changed['2']['stack']['mover']=body(-.9)
        self.assertTrue(any('action/reaction' in error for error in force_level_checks(changed,[1,2])))

    def test_separate_body_quadrature_is_explicit_and_refined_in_both(self):
        self.assertEqual(quadrature_levels([3,4],[0,1]),{'mover':[3,4],'stator':[0,1]})
        self.assertEqual(quadrature_levels([1,2]),{'mover':[1,2],'stator':[1,2]})
        for mover,stator in [([1],[0]),([3,4],[1]),([3,4],[1,1]),([3,4],[1,7])]:
            with self.assertRaises(ValueError):quadrature_levels(mover,stator)

    def test_incomplete_changed_or_wrong_kind_results_are_not_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);job=work/'bare';job.mkdir()
            for name in ['reaction.pos','project.pro']:(job/name).write_text('original '+name)
            (work/'project.msh').write_text('mesh')
            (job/'solve.log').write_text('CONVERGED_RTOL')
            success={'status':'completed','exit_code':0,'command':['getdp','project.pro','-setnumber','Mode','0']}
            receipt=job/'solve.log.command.json';receipt.write_text(json.dumps(success))
            source={'method':'analytic-source-reduced-scalar-potential','status':'completed-reduced-response-fields-unqualified',
                    'failures':[],'mesh_sha256':sha(work/'project.msh'),
                    'runs':{'bare':{'mode':0,'reaction_field_sha256':sha(job/'reaction.pos'),'formulation_sha256':sha(job/'project.pro')}}}
            self.assertEqual(case_field(work,source,'bare'),job/'reaction.pos')
            for key,value in [('status','running'),('status','failed'),('method','old-total-potential'),('failures',['failed'])]:
                changed=dict(source);changed[key]=value
                with self.assertRaises(ValueError):case_field(work,changed,'bare')
            receipt.write_text(json.dumps({'status':'timeout'}))
            with self.assertRaises(ValueError):case_field(work,source,'bare')
            receipt.write_text(json.dumps(dict(success,command=['getdp','project.pro','-setnumber','Mode','2'])))
            with self.assertRaises(ValueError):case_field(work,source,'bare')
            receipt.write_text(json.dumps(success))
            (job/'reaction.pos').write_text('changed field')
            with self.assertRaises(ValueError):case_field(work,source,'bare')
