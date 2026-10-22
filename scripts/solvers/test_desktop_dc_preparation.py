import unittest

from desktop_dc_preparation import DISK_LIMIT,DISK_RESERVE,MEMORY_LIMIT,resource_violation
from dc_preparation import PREPARATION_TIMEOUT


class PreparationResourceGuardTest(unittest.TestCase):
    def test_native_memory_whole_timeout_and_disk_are_independent_stops(self):
        self.assertIsNone(resource_violation(MEMORY_LIMIT,PREPARATION_TIMEOUT-1,DISK_LIMIT,DISK_RESERVE))
        for values,status in [((MEMORY_LIMIT+1,0,0,DISK_RESERVE),'memory-limit'),
            ((0,PREPARATION_TIMEOUT,0,DISK_RESERVE),'timeout'),((0,0,DISK_LIMIT+1,DISK_RESERVE),'disk-limit'),
            ((0,0,0,DISK_RESERVE-1),'disk-limit')]:
            with self.subTest(status=status):self.assertEqual(resource_violation(*values)[0],status)
