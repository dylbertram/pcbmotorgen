from copy import deepcopy
import unittest

from linear_dc_mesh_checkpoint import validate_checkpoint


class EndedMeshCheckpointTest(unittest.TestCase):
    def inputs(self):
        expected=dict(version='pinned',input_hashes={'physical':'same'},geometry={'return':'actual'},brep_sha256='cad',
            request=dict(mesh_m=.0002,curvature_safety=6.,port_fraction=.5,max_dofs=24000000),study_bindings={'declared':'same'})
        prior=dict(deepcopy(expected),status='running',estimated_dofs=12000000,materials=['copper','drive'],
            geometric_volume_check=dict(relative_difference=.001),cad_partition_checks=dict(physical_union_relative_error=1e-11,drive_volume_relative_error=0.))
        return prior,expected,dict(status='memory-limit')

    def test_only_mesh_reuse_after_resource_failure_and_passed_geometry_gates(self):
        prior,expected,receipt=self.inputs();validate_checkpoint(prior,expected,receipt)
        for change in ['live','field','port','physical','volume','dofs']:
            p,e,r=self.inputs()
            if change=='live':r['status']='running'
            elif change=='field':p['solution_sha256']='unaccepted-field'
            elif change=='port':p['request']['port_fraction']=.4
            elif change=='physical':p['input_hashes']['physical']='other'
            elif change=='volume':p['geometric_volume_check']['relative_difference']=.03
            else:p['estimated_dofs']=25000000
            with self.subTest(change=change),self.assertRaises(ValueError):validate_checkpoint(p,e,r)

    def test_a_numerical_failure_is_not_a_resource_checkpoint(self):
        prior,expected,receipt=self.inputs();receipt['status']='failed'
        with self.assertRaises(ValueError):validate_checkpoint(prior,expected,receipt)

    def test_completed_mesh_only_can_start_a_fresh_current_solve(self):
        prior,expected,receipt=self.inputs();prior['status']='completed-linear-study-mesh-only'
        prior['request']['mesh_only']=True;expected['request']['mesh_only']=False
        receipt.update(status='completed',exit_code=0);validate_checkpoint(prior,expected,receipt)
        for invalid in [False,0.,'0',None]:
            receipt['exit_code']=invalid
            with self.subTest(exit_code=invalid),self.assertRaises(ValueError):validate_checkpoint(prior,expected,receipt)
