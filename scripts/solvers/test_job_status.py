import os
import subprocess
import sys
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from job_status import process_identity,receipt_liveness,inspect


class JobStatusTest(unittest.TestCase):
    def test_explicit_external_supervisor_receipt_is_observed_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'job';work.mkdir()
            receipt=root/'supervisor.command.json';receipt.write_text(json.dumps({'status':'timeout'}))
            summary=work/'summary.json';summary.write_text(json.dumps({'status':'running','command_receipt':str(receipt)}))
            before=(summary.read_bytes(),receipt.read_bytes())
            result=inspect(work)
            self.assertEqual(result['observed_status'],'incomplete-with-failed-child')
            self.assertEqual((summary.read_bytes(),receipt.read_bytes()),before)

    def test_standalone_reports_cannot_hide_an_interrupted_or_missing_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);report=root/'force.json';receipt=root/'force.command.json'
            report.write_text(json.dumps({'status':'passed-force-controls'}))
            receipt.write_text(json.dumps({'status':'interrupted'}))
            self.assertEqual(inspect(root,report,receipt)['observed_status'],'incomplete-with-failed-child')
            receipt.write_text(json.dumps({'status':'completed','exit_code':0}))
            # An unrelated failed run in the shared prefix must not taint this report.
            (root/'other.command.json').write_text(json.dumps({'status':'timeout'}))
            self.assertEqual(inspect(root,report,receipt)['observed_status'],'passed-force-controls')
            receipt.unlink()
            self.assertEqual(inspect(root,report,receipt)['observed_status'],'unverified-result')

    @unittest.skipUnless(sys.platform in ['linux','darwin'],'Linux/macOS process identity')
    def test_live_child_and_reaped_child_are_distinct(self):
        with subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']) as child:
            try:
                identity=process_identity(child.pid)
                self.assertIsNotNone(identity)
                receipt={'status':'running','pid':child.pid,'process_identity':identity}
                self.assertEqual(receipt_liveness(receipt)['state'],'live-worker')
            finally:
                child.terminate();child.wait(timeout=5)
        self.assertEqual(receipt_liveness(receipt)['state'],'stale-running')

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
            for invalid in [{},dict(expected,start_ticks=True),dict(expected,boot_id='')]:
                self.assertEqual(receipt_liveness(dict(receipt,process_identity=invalid))['state'],'unknown')
        with patch('job_status.process_identity',return_value={'pid':1234,'state':'unknown'}):
            self.assertEqual(receipt_liveness(receipt)['state'],'unknown')

    def test_running_without_worker_identity_is_not_progress_evidence(self):
        for pid in [None,True,1,'123']:
            self.assertEqual(receipt_liveness({'status':'running','pid':pid})['state'],'unknown')
