import unittest

from package_housing_harmonic_release import verify_unittest_inventory


class HarmonicReleaseInventoryTest(unittest.TestCase):
    def test_whole_successful_count_is_verified(self):
        verify_unittest_inventory('...\nRan 311 tests in 29.0s\n\nOK\n', 311)

    def test_discovered_tests_with_skips_cannot_be_claimed_as_passes(self):
        for skipped in [4, 5]:
            with self.assertRaises(ValueError):
                verify_unittest_inventory(f'...\nRan 306 tests in 28.0s\n\nOK (skipped={skipped})\n', 306)

    def test_wrong_count_failed_or_partial_runs_are_rejected(self):
        for text in ['Ran 310 tests in 1s\n\nOK\n',
                     'Ran 311 tests in 1s\n\nFAILED (failures=1)\n',
                     'Ran 311 tests in 1s\n',
                     'Ran 311 tests in 1s\n\nOK\ninterrupted']:
            with self.assertRaises(ValueError):
                verify_unittest_inventory(text, 311)


if __name__ == '__main__':
    unittest.main()
