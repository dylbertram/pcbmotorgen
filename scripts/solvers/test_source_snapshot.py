import tempfile
import unittest
from pathlib import Path

from source_snapshot import capture


class SourceSnapshotTest(unittest.TestCase):
    def test_changed_sources_keep_both_versions_and_corrupt_snapshots_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory).resolve();source=work/'analysis.py';source.write_text('original\n')
            first=capture(work,[source])[str(source)]
            source.write_text('updated\n')
            second=capture(work,[source])[str(source)]
            self.assertNotEqual(first['sha256'],second['sha256'])
            self.assertEqual((work/first['snapshot']).read_text(),'original\n')
            (work/second['snapshot']).write_text('corrupt\n')
            with self.assertRaises(ValueError):capture(work,[source])


if __name__=='__main__':
    unittest.main()
