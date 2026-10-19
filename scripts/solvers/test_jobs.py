import subprocess
import os
import signal
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from check_free_space import run


def fake_process(output, code=0, error=None):
    process=MagicMock()
    process.pid=42424242
    process.wait.side_effect=[error,code] if error else None
    process.wait.return_value=code

    def start(*args,**kwargs):
        kwargs['stdout'].write(output)
        kwargs['stdout'].flush()
        return process
    return process,start


class JobFailureTest(unittest.TestCase):
    def test_failed_or_unconverged_jobs_never_pass(self):
        for code, output in [(1, "crashed"), (-15, "cancelled"), (0, "DIVERGED_ITS"),
                             (0, "Error   : invalid material"), (0, "ERROR:: bad input"),
                             (0, "NOT CONVERGED")]:
            with self.subTest(code=code, output=output), tempfile.TemporaryDirectory() as directory:
                work=Path(directory)
                process,start=fake_process(output,code)
                with patch('check_free_space.subprocess.Popen',side_effect=start),patch('check_free_space.os.killpg',create=True) as group_kill:
                    with self.assertRaises(RuntimeError):
                        run(['solver'],work,'job.log')
                self.assertEqual((work/'job.log').read_text(),output)
                receipt=json.loads((work/'job.log.command.json').read_text())
                self.assertEqual(receipt['status'],'failed')
                self.assertEqual(receipt['exit_code'],code)
                process.kill.assert_not_called()
                if os.name=='posix':group_kill.assert_called_once_with(process.pid,signal.SIGKILL)

    def test_timeout_retains_live_diagnostics_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            process,start=fake_process('partial output',error=subprocess.TimeoutExpired('solver',600))
            with patch('check_free_space.subprocess.Popen',side_effect=start),patch('check_free_space.os.killpg',create=True) as group_kill:
                with self.assertRaisesRegex(RuntimeError,'timed out'):
                    run(['solver'],work,'job.log')
            self.assertIn('partial output',(work/'job.log').read_text())
            self.assertIn('FAILED',(work/'job.log').read_text())
            self.assertEqual(json.loads((work/'job.log.command.json').read_text())['status'],'timeout')
            if os.name=='posix':group_kill.assert_called_once_with(process.pid,signal.SIGKILL)
            else:process.kill.assert_called_once()
            self.assertEqual(process.wait.call_count,2)

    def test_interrupted_job_is_reaped_and_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            process,start=fake_process('partial output',error=KeyboardInterrupt())
            with patch('check_free_space.subprocess.Popen',side_effect=start),patch('check_free_space.os.killpg',create=True) as group_kill:
                with self.assertRaises(KeyboardInterrupt):
                    run(['solver'],work,'job.log')
            receipt=json.loads((work/'job.log.command.json').read_text())
            self.assertEqual(receipt['status'],'interrupted')
            self.assertNotIn('exit_code',receipt)
            if os.name=='posix':group_kill.assert_called_once_with(process.pid,signal.SIGKILL)
            else:process.kill.assert_called_once()

    def test_success_retains_command_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            _,start=fake_process('converged')
            with patch('check_free_space.subprocess.Popen',side_effect=start),patch('check_free_space.os.killpg',create=True) as group_kill:
                self.assertGreaterEqual(run(['solver','-solve'],work,'job.log'),0)
            receipt=json.loads((work/'job.log.command.json').read_text())
            self.assertEqual(receipt['status'],'completed')
            self.assertEqual(receipt['command'],['solver','-solve'])
            self.assertEqual(receipt['exit_code'],0)
            group_kill.assert_not_called()

    def test_mocked_or_unsafe_pid_never_reaches_an_os_signal(self):
        for pid in [MagicMock(),1,0,-1,True]:
            with self.subTest(pid=pid),tempfile.TemporaryDirectory() as directory:
                work=Path(directory);process,start=fake_process('fixture');process.pid=pid
                with patch('check_free_space.subprocess.Popen',side_effect=start),patch('check_free_space.os.killpg',create=True) as group_kill:
                    with self.assertRaisesRegex(ValueError,'safe owned PID'):run(['solver'],work,'invalid.log')
                group_kill.assert_not_called();process.kill.assert_not_called()
                self.assertEqual(json.loads((work/'invalid.log.command.json').read_text())['status'],'invalid-process-handle')


if __name__=='__main__':
    unittest.main()
