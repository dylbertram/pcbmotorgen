import tempfile
import unittest
from pathlib import Path
import sys

from benchmark_solver_threads import interpreter_path


class ThreadBenchmarkInterpreterTest(unittest.TestCase):
    def test_keeps_the_virtual_environment_entry_point(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'python';path.symlink_to(sys.executable)
            self.assertEqual(interpreter_path(path),str(path.absolute()))
            self.assertNotEqual(interpreter_path(path),str(path.resolve()))
