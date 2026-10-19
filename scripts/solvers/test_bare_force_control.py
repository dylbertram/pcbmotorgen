import unittest

from post_project_bare_force import require_bare_control


class BareForceControlTest(unittest.TestCase):
    def test_partial_or_failed_material_job_cannot_be_relabelled_as_control(self):
        for status in ['running','failed','comparison-only','completed-bare-field-only-unqualified']:
            with self.assertRaises(ValueError):require_bare_control({'status':status,'failures':[]})
        record={'status':'completed-bare-field-only-unqualified','failures':[],
                'runs':{'bare':{'magpylib_vector_error':0.01}}}
        require_bare_control(record)
        for invalid in [0.1,float('nan'),-1,True]:
            record['runs']['bare']['magpylib_vector_error']=invalid
            with self.assertRaises(ValueError):require_bare_control(record)
