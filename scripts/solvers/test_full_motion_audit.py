import copy
import unittest

from audit_housing_full_controls import change


class FullStrokeAuditTest(unittest.TestCase):
    def test_complete_energy_history_is_checked_even_with_zero_final_energy(self):
        base={'joule_energy_j':1.,'source_work_energy_j':1.,'profile':{'dt_s':1.},
            'steps':[{'time_mid_s':i+.5,'housing_source_interaction_force_n':[1.,0.,0.],
                      'reaction_energy_end_j':e} for i,e in enumerate([.1,.2,.1,0.])]}
        same=copy.deepcopy(base)
        self.assertTrue(change(base,same)['passed'])
        same['steps'][1]['reaction_energy_end_j']=.3
        self.assertFalse(change(base,same)['passed'])
