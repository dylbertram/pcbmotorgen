import copy
import unittest

import numpy as np

from check_finite_convergence import assess, validate_refinement


def fixture():
    table=np.zeros((25,6));table[:,5]=1
    fields={tag:{mode:table.copy() for mode in ['bare','linear','nonlinear']} for tag in ['coarse','fine','domain']}
    force={'status':'comparison-only','surfaces':{str(c):{'bare':[0,0,0],'linear':[0,0,2],'nonlinear':[0,0,1]} for c in [0.0004,0.0006,0.0008]}}
    forces={tag:{n:copy.deepcopy(force) for n in [32,64]} for tag in fields}
    return fields,forces


class FiniteGateTest(unittest.TestCase):
    def test_refinement_labels_cannot_substitute_for_changed_inputs(self):
        requests={'coarse':{'mesh':0.0008,'gap_mesh':0.0003,'radius':0.03},
                  'fine':{'mesh':0.0006,'gap_mesh':0.0002,'radius':0.03},
                  'domain':{'mesh':0.0006,'gap_mesh':0.0002,'radius':0.045}}
        validate_refinement(requests)
        for tag,key,value in [('fine','mesh',0.0008),('fine','radius',0.045),
                              ('domain','gap_mesh',0.0001),('domain','radius',0.03)]:
            changed=copy.deepcopy(requests);changed[tag][key]=value
            with self.assertRaises(ValueError):validate_refinement(changed)

    def test_all_independent_gates_pass(self):
        self.assertEqual(assess(*fixture())[1],[])

    def test_unconverged_or_null_data_cannot_pass(self):
        fields,forces=fixture()
        fields['domain']['nonlinear'][:,5]*=1.2
        self.assertTrue(any('field change' in value for value in assess(fields,forces)[1]))
        fields['domain']['nonlinear'][:,5]=0
        with self.assertRaises(ValueError):assess(fields,forces)

    def test_force_floor_symmetry_and_surface_are_checked(self):
        for mode,value,fragment in [('bare',[0,0,0.1],'floor'),('nonlinear',[0.1,0,1],'symmetry'),
                                    ('linear',[0,0,2.2],'sensitivity')]:
            fields,forces=fixture()
            forces['fine'][64]['surfaces']['0.0004'][mode]=value
            self.assertTrue(any(fragment in item for item in assess(fields,forces)[1]))


if __name__=='__main__':
    unittest.main()
