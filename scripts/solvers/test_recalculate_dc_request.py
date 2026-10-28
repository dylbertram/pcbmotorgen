import hashlib
from pathlib import Path
import tempfile
import unittest

from recalculate_dc_request import unchanged_request_bytes


class LiveRequestFreshnessTest(unittest.TestCase):
    def test_changed_request_content_cannot_return_old_force(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'request.json'
            original = b'{"current_a":0.1}'
            path.write_bytes(original)
            digest = hashlib.sha256(original).hexdigest()
            self.assertEqual(unchanged_request_bytes(path, digest), original)
            path.write_bytes(b'{"current_a":0.5}')
            with self.assertRaisesRegex(ValueError, 'stale'):
                unchanged_request_bytes(path, digest)
