from datetime import datetime,timezone
import tempfile
from pathlib import Path
import unittest

from post_project_force import sha
from run_declared_solver_job import validate_job


class DeclaredJobPolicyTest(unittest.TestCase):
    def test_actual_inputs_deadline_memory_and_log_are_bound_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();source=root/'actual.json';source.write_text('actual-input')
            spec=dict(schema='bounded-solver-job-v1',cutoff_utc='2026-10-22T19:59:49Z',timeout_s=3600,
                native_footprint_limit_bytes=18*1024**3,command=['python','solver.py'],log='unique.log',
                archive_root=str(root),input_hashes={str(source):sha(source)})
            now=datetime(2026,10,22,8,tzinfo=timezone.utc);validate_job(spec,now)
            with self.assertRaisesRegex(ValueError,'Entire job budget'):validate_job(spec,datetime(2026,10,22,19,tzinfo=timezone.utc))
            for key,value in [('log','../outside.log'),('native_footprint_limit_bytes',19*1024**3),('timeout_s',True),('command',[])]:
                with self.subTest(key=key),self.assertRaises(ValueError):validate_job(spec|{key:value},now)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'input changed'):validate_job(spec,now)
