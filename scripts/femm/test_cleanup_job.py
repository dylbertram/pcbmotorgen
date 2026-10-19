import signal
import tempfile
import unittest
from pathlib import Path

from cleanup_job import cleanup


class CleanupTest(unittest.TestCase):
    def test_cleanup_is_scoped_to_executable_prefix_and_exact_job_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for pid, exe, prefix, job in [
                (100, "fkn.exe", "/prefix", "one"),
                (101, "triangle.exe", "/prefix", "one"),
                (102, "fkn.exe", "/other-prefix", "one"),
                (103, "fkn.exe", "/prefix", "one-more"),
                (104, "other.exe", "/prefix", "one"),
            ]:
                p = root / str(pid)
                p.mkdir()
                (p / "cmdline").write_bytes(f"C:\\femm42\\bin\\{exe}\0z:\\runs\\{job}\\case\0".encode())
                (p / "environ").write_bytes(f"WINEPREFIX={prefix}\0".encode())
            killed = []
            self.assertEqual(sorted(cleanup("/prefix", "/runs/one", root, lambda *args: killed.append(args))), [100, 101])
            self.assertEqual(sorted(killed), [(100, signal.SIGKILL), (101, signal.SIGKILL)])
            with self.assertRaises(ValueError):
                cleanup("/prefix", "/", root, lambda *_: None)


if __name__ == "__main__":
    unittest.main()
