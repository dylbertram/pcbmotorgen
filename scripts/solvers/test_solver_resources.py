import unittest

from solver_resources import getdp_resources


class SolverResourceTest(unittest.TestCase):
    def test_completed_and_incomplete_logs_have_distinct_resource_evidence(self):
        log='Info : System 1/1: 21899 Dofs\nInfo : Stopped (today, Wall = 53.6496s, CPU = 49.6705s, Mem = 208.059Mb)\n'
        values=getdp_resources(log)
        self.assertEqual(values['max_reported_dofs'],21899)
        self.assertEqual(values['solver_reported_final_memory_mb'],208.059)
        self.assertNotIn('solver_reported_final_memory_mb',getdp_resources(log.split('Info : Stopped')[0]))
        self.assertEqual(getdp_resources('killed before assembly'),{})

    def test_invalid_resource_values_are_not_performance_evidence(self):
        with self.assertRaises(ValueError):getdp_resources('Info : System 1/1: 0 Dofs')
        with self.assertRaises(ValueError):getdp_resources('Info : Stopped (today, Wall = -1s, CPU = 2s, Mem = 3Mb)')


if __name__=='__main__':unittest.main()
