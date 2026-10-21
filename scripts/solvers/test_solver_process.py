import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from check_free_space import run
from job_status import process_identity


class SolverProcessTest(unittest.TestCase):
    def assert_stopped(self,pid):
        deadline=time.monotonic()+2
        while True:
            status=process_identity(pid)
            if status is None or status['state']=='Z':return
            if time.monotonic()>deadline:self.fail(f'Owned process {pid} survived cleanup')
            time.sleep(0.01)

    def test_success_and_zero_exit_unconverged_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            run([sys.executable,'-c','print("converged fixture")'],work,'good.log')
            receipt=json.loads((work/'good.log.command.json').read_text())
            self.assertEqual(receipt['status'],'completed');self.assertEqual(receipt['exit_code'],0)
            with self.assertRaises(RuntimeError):run([sys.executable,'-c','print("DIVERGED_ITS")'],work,'bad.log')
            receipt=json.loads((work/'bad.log.command.json').read_text())
            self.assertEqual(receipt['status'],'failed');self.assertEqual(receipt['exit_code'],0)

    def test_spawn_failure_does_not_leave_a_running_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            with self.assertRaises(FileNotFoundError):run([str(work/'nonexistent-solver')],work,'spawn.log')
            self.assertEqual(json.loads((work/'spawn.log.command.json').read_text())['status'],'spawn-failed')

    def test_invalid_timeout_does_not_start_a_process(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'PCB_MOTOR_SOLVER_TIMEOUT':'nan'}):
            work=Path(directory)
            with self.assertRaises(ValueError):run([sys.executable,'-c','raise AssertionError()'],work,'invalid.log')
            self.assertFalse((work/'invalid.log').exists())

    @unittest.skipUnless(sys.platform in ['linux','darwin'],'Linux/macOS process-tree cleanup evidence')
    def test_timeout_stops_the_owned_solver_and_its_child(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'PCB_MOTOR_SOLVER_TIMEOUT':'0.7'}):
            work=Path(directory)
            program='import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); Path("child.pid").write_text(str(p.pid)); time.sleep(60)'
            with self.assertRaisesRegex(RuntimeError,'timed out'):run([sys.executable,'-c',program],work,'timeout.log')
            receipt=json.loads((work/'timeout.log.command.json').read_text())
            self.assertEqual(receipt['status'],'timeout');self.assertEqual(receipt['cleanup_scope'],'owned-posix-process-group')
            for pid in [receipt['pid'],int((work/'child.pid').read_text())]:
                self.assert_stopped(pid)

    @unittest.skipUnless(sys.platform in ['linux','darwin'],'Linux/macOS process-tree cleanup evidence')
    def test_failed_parent_cannot_leave_its_child_running(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            program='import subprocess,sys; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); Path("child.pid").write_text(str(p.pid)); sys.exit(3)'
            with self.assertRaises(RuntimeError):run([sys.executable,'-c',program],work,'failed.log')
            receipt=json.loads((work/'failed.log.command.json').read_text())
            self.assertEqual(receipt['status'],'failed');self.assertEqual(receipt['exit_code'],3)
            self.assert_stopped(int((work/'child.pid').read_text()))

    @unittest.skipUnless(sys.platform in ['linux','darwin'],'Linux/macOS SIGTERM cleanup evidence')
    def test_sigterm_of_supervisor_cleans_up_solver_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            solver='import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); Path("child.pid").write_text(str(p.pid)); time.sleep(60)'
            supervisor=f'import sys; from pathlib import Path; sys.path.insert(0,{str(Path(__file__).resolve().parent)!r}); from check_free_space import run; run([sys.executable,"-c",{solver!r}],Path.cwd(),"cancel.log")'
            with subprocess.Popen([sys.executable,'-c',supervisor],cwd=work) as process:
                try:
                    deadline=time.monotonic()+10
                    while not (work/'child.pid').exists():
                        if process.poll() is not None or time.monotonic()>deadline:self.fail('Supervisor did not launch fixture')
                        time.sleep(0.01)
                    process.terminate();self.assertEqual(process.wait(timeout=5),143)
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=5)
            receipt=json.loads((work/'cancel.log.command.json').read_text())
            self.assertEqual(receipt['status'],'interrupted')
            for pid in [receipt['pid'],int((work/'child.pid').read_text())]:self.assert_stopped(pid)


if __name__=='__main__':unittest.main()
