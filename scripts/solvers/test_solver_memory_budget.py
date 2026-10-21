import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from solver_memory_budget import MemoryBudgetExceeded,process_memory,wait_guarded


class NativeMemoryBudgetTest(unittest.TestCase):
    def test_samples_peak_and_finishes_without_changing_result(self):
        process=Mock(pid=123,args=['solver']);process.wait.side_effect=[subprocess.TimeoutExpired(['solver'],1),0]
        observed=[]
        with patch('solver_memory_budget.time.monotonic',side_effect=[0.,0.,0.,1.,1.]):
            result=wait_guarded(process,10.,100,observed.append,observe=lambda pid:dict(physical_footprint_bytes=42))
        self.assertEqual(result,0);self.assertEqual(len(observed),2)
        self.assertEqual(observed[-1]['peak_physical_footprint_bytes'],42)

    def test_exceeded_budget_never_waits_for_solver_completion(self):
        process=Mock(pid=123,args=['solver'])
        with self.assertRaises(MemoryBudgetExceeded):
            wait_guarded(process,10.,100,lambda value:None,observe=lambda pid:dict(physical_footprint_bytes=101))
        process.wait.assert_not_called()
        for limit in [0,-1,True,1.5]:
            with self.subTest(limit=limit),self.assertRaises(ValueError):wait_guarded(process,10.,limit,lambda value:None)

    @unittest.skipUnless(sys.platform=='darwin','native macOS physical-footprint API')
    def test_native_probe_and_real_owned_group_cleanup_on_budget_failure(self):
        from check_free_space import run
        import json
        value=process_memory(os.getpid());self.assertGreater(value['physical_footprint_bytes'],0)
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            with self.assertRaisesRegex(RuntimeError,'memory budget exceeded'):
                run([sys.executable,'-c','import time; time.sleep(30)'],work,'budget.log',memory_limit_bytes=1)
            receipt=json.loads((work/'budget.log.command.json').read_text())
            self.assertEqual(receipt['status'],'memory-limit')
            self.assertFalse((work/'budget.log.command.json.memory.json').exists())
            self.assertTrue((work/'budget.log.command.memory.json').exists())
            with self.assertRaises(ProcessLookupError):os.kill(receipt['pid'],0)
