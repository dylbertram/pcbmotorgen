from pathlib import Path
import tempfile
import unittest
from unittest import mock

import check_dc_worker


class PinnedWorkerEnvironmentTest(unittest.TestCase):
    def test_preparation_mode_adds_only_the_explicitly_pinned_source_dependency(self):
        path=check_dc_worker.HERE/'requirements-dc-worker.txt'
        magnetic=check_dc_worker.required_packages(path)
        preparation=check_dc_worker.required_packages(path,True)
        self.assertNotIn('pyamg',magnetic)
        self.assertEqual(preparation,magnetic|{'pyamg':'5.3.0'})

    def test_magnetic_only_install_does_not_claim_source_preparation(self):
        def version(name):
            if name=='pyamg':raise check_dc_worker.metadata.PackageNotFoundError(name)
            return check_dc_worker.pins(check_dc_worker.HERE/'requirements-dc-worker.txt')[name]
        with mock.patch('check_dc_worker.metadata.version',side_effect=version):
            self.assertEqual(check_dc_worker.problems(check_dc_worker.required_packages(check_dc_worker.HERE/'requirements-dc-worker.txt')),[])
            found=check_dc_worker.problems(check_dc_worker.required_packages(check_dc_worker.HERE/'requirements-dc-worker.txt',True))
        self.assertEqual(found,['missing pyamg==5.3.0'])

    def test_pins_parse_exact_versions_and_mismatches_are_named(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'pins.txt'
            path.write_text('# comment\nnumpy==1.0\nNetgen_OCCT==7.8.1\n')
            self.assertEqual(check_dc_worker.pins(path), {'numpy': '1.0', 'netgen-occt': '7.8.1'})
        with mock.patch('check_dc_worker.metadata.version', side_effect=lambda name: {'numpy': '2.0'}[name]):
            found = check_dc_worker.problems({'numpy': '1.0'})
        self.assertIn('numpy 2.0 differs from pinned 1.0', found)

    def test_missing_distribution_and_wrong_interpreter_are_rejected(self):
        def version(name):
            raise check_dc_worker.metadata.PackageNotFoundError(name)
        with mock.patch('check_dc_worker.metadata.version', side_effect=version):
            found = check_dc_worker.problems({'ngsolve': '6.2.2608'}, python=(3, 99))
        self.assertIn('missing ngsolve==6.2.2608', found)
        self.assertTrue(any('differs from qualified 3.99' in item for item in found))

    def test_current_qualified_environment_passes(self):
        self.assertEqual(check_dc_worker.problems(check_dc_worker.pins(check_dc_worker.HERE/'requirements-dc-worker.txt')), [])
