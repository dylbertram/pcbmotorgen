import unittest

from audit_plate2d import require_convergence, assess


class PlateAuditTest(unittest.TestCase):
    def test_finished_process_is_not_nonlinear_convergence(self):
        for value in ['0.14522590E-06','nan']:
            log=f'ComputeChange: NS (ITER=100) (NRM,RELC): ( 0.001 {value} ) :: vectorpotential\nSystem has converged to tolerances'
            with self.assertRaises(ValueError):require_convergence(log,'elmer',True)
        with self.assertRaises(ValueError):require_convergence('ELMER SOLVER FINISHED AT:','elmer',True)
        require_convergence('ComputeChange: NS (ITER=20) (NRM,RELC): ( 0.001 1e-10 ) :: vectorpotential\nSystem has converged to tolerances','elmer',True)

    def test_subset_still_requires_all_numerical_gates(self):
        runs={tag:{'reference':{'pressure_pa':100},'bare':{'stress_path_pressures_pa':[0,0,0]},
                   'plate':{'pressure_pa':100,'stress_path_pressures_pa':[100,100,100]},
                   'field_ratio_error':0,'pressure_error':0,'field_ratio':1.3,'pressure_pa':100}
              for tag in ['base','fine','domain']}
        self.assertEqual(assess(runs),[])
        runs['fine']['plate']['stress_path_pressures_pa'][0]=110
        self.assertTrue(any('stress-path' in value for value in assess(runs)))


if __name__=='__main__':
    unittest.main()
