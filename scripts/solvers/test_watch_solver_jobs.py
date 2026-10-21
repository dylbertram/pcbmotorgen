import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watch_solver_jobs import observe,descendants,summary_path


class SolverWatchTest(unittest.TestCase):
    def fixture(self,folder,status='running',exit_code=None):
        root=Path(folder);receipt=root/'test.log.command.json';summary=root/'summary.json';log=root/'test.log'
        receipt.write_text(json.dumps({'status':status,'exit_code':exit_code,'pid':123,'command':['python','script','--work',str(root)]}))
        summary.write_text(json.dumps({'status':'running','steps':[{}]}));log.write_text('working\n')
        return receipt,summary,log

    def test_nested_worker_resources_include_time_wrapper_children(self):
        values=descendants(10,{10:{'parent':1,'cpu_percent':0.,'rss_bytes':100},
            11:{'parent':10,'cpu_percent':1200.,'rss_bytes':1000},12:{'parent':2,'cpu_percent':20.,'rss_bytes':500}})
        self.assertEqual(values['cpu_percent'],1200.);self.assertEqual(values['rss_bytes'],1100)

    def test_busy_file_silence_is_not_failure(self):
        with tempfile.TemporaryDirectory() as folder,patch('watch_solver_jobs.receipt_liveness',return_value={'state':'live-worker'}):
            receipt,_,_=self.fixture(folder);table={123:{'parent':1,'cpu_percent':1200.,'rss_bytes':100}}
            first=observe(receipt,{},0.,table,60.);second=observe(receipt,first,120.,table,60.)
            self.assertEqual(second['activity'],'busy-without-new-file-output');self.assertEqual(second['alerts'],[])

    def test_no_progress_idle_warns_but_does_not_modify_inputs(self):
        with tempfile.TemporaryDirectory() as folder,patch('watch_solver_jobs.receipt_liveness',return_value={'state':'live-worker'}):
            receipt,summary,log=self.fixture(folder);before=[p.read_bytes() for p in [receipt,summary,log]]
            table={123:{'parent':1,'cpu_percent':0.,'rss_bytes':100}}
            first=observe(receipt,{},0.,table,60.);second=observe(receipt,first,120.,table,60.)
            self.assertTrue(second['alerts']);self.assertEqual(before,[p.read_bytes() for p in [receipt,summary,log]])

    def test_stale_pid_requires_consecutive_observations(self):
        with tempfile.TemporaryDirectory() as folder,patch('watch_solver_jobs.receipt_liveness',return_value={'state':'stale-running'}):
            receipt,_,_=self.fixture(folder)
            first=observe(receipt,{},0.,{},60.);self.assertFalse(first['alerts'])
            self.assertTrue(observe(receipt,first,60.,{},60.)['alerts'])

    def test_new_traceback_and_terminal_timeout_are_flagged(self):
        with tempfile.TemporaryDirectory() as folder,patch('watch_solver_jobs.receipt_liveness',return_value={'state':'live-worker'}):
            receipt,_,log=self.fixture(folder);first=observe(receipt,{},0.,{},60.)
            log.write_text(log.read_text()+'Traceback (most recent call last):\n')
            self.assertTrue(observe(receipt,first,1.,{},60.)['alerts'])
            receipt.write_text(json.dumps({'status':'timeout'}))
            self.assertTrue(observe(receipt,{},2.,{},60.)['alerts'])

    def test_completed_process_is_not_automatic_numerical_success(self):
        with tempfile.TemporaryDirectory() as folder,patch('watch_solver_jobs.receipt_liveness',return_value={'state':'not-running'}):
            receipt,summary,_=self.fixture(folder,'completed',0)
            self.assertTrue(observe(receipt,{},0.,{},60.)['alerts'])
            summary.write_text(json.dumps({'status':'passed-limited-audit','failures':[]}))
            self.assertFalse(observe(receipt,{},1.,{},60.)['alerts'])

    def test_output_file_is_not_confused_with_source_work(self):
        self.assertEqual(summary_path({'command':['x','--source-work','old','--output','audit.json']},Path('/data')),Path('/data/audit.json'))
