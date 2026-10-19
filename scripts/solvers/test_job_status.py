import os
import unittest
from unittest.mock import patch

from job_status import process_identity,receipt_liveness


class JobStatusTest(unittest.TestCase):
    def test_real_process_identity_and_terminal_receipts(self):
        own=process_identity(os.getpid())
        self.assertEqual(own['pid'],os.getpid())
        self.assertGreater(own['start_ticks'],0)
        self.assertEqual(receipt_liveness({'status':'timeout'})['state'],'not-running')
        self.assertIsNone(process_identity(True));self.assertIsNone(process_identity(1))

    def test_absent_zombie_and_reused_pids_are_not_live(self):
        expected={'pid':1234,'start_ticks':20,'boot_id':'old','pid_namespace':'pid:[1]','state':'R'}
        receipt={'status':'running','pid':1234,'process_identity':expected}
        for observed in [None,dict(expected,state='Z'),dict(expected,start_ticks=21),dict(expected,boot_id='new'),dict(expected,pid_namespace='pid:[2]')]:
            with patch('job_status.process_identity',return_value=observed):
                self.assertEqual(receipt_liveness(receipt)['state'],'stale-running')
        with patch('job_status.process_identity',return_value=expected):
            self.assertEqual(receipt_liveness(receipt)['state'],'live-worker')
            self.assertEqual(receipt_liveness({'status':'running','pid':1234})['state'],'unknown')

    def test_running_without_worker_identity_is_not_progress_evidence(self):
        for pid in [None,True,1,'123']:
            self.assertEqual(receipt_liveness({'status':'running','pid':pid})['state'],'unknown')
