"""Inventory parsing and preservation tests; no legal-clearance assertions."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from audit_dc_worker_native import digest, license_files, linkage, main


class NativeInventoryTest(unittest.TestCase):
    def test_existing_inventory_is_not_overwritten_or_recomputed(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'inventory.json';path.write_text('original evidence\n')
            with patch('sys.argv',['audit_dc_worker_native.py','--output',str(path)]), \
                 patch('audit_dc_worker_native.inventory') as inventory, \
                 self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code,2);inventory.assert_not_called()
            self.assertEqual(path.read_text(),'original evidence\n')

    def test_license_evidence_has_original_file_hash_and_size(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'LICENSE').write_text('example notice\n');(root/'module.py').write_text('pass\n')
            dist=SimpleNamespace(files=['LICENSE','module.py'],locate_file=lambda item:root/item)
            self.assertEqual(license_files(dist),[dict(path=str((root/'LICENSE').resolve()),sha256=digest(root/'LICENSE'),bytes=15)])

    def test_linkage_keeps_relocatable_paths_unresolved(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'module.so';path.write_bytes(b'example image')
            result=SimpleNamespace(returncode=0,stdout=str(path)+':\n\t@rpath/libworker.dylib (compatibility version 1.0.0)\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n')
            with patch('audit_dc_worker_native.subprocess.run',return_value=result):report=linkage(path)
            self.assertEqual(report['relocatable_dependencies'],['@rpath/libworker.dylib'])
            self.assertEqual(report['sha256'],digest(path))
            self.assertEqual(len(report['dependencies']),2)

    def test_non_file_and_failed_inspection_are_not_reported_as_inspected(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'missing.dylib'
            self.assertEqual(linkage(path)['status'],'not-a-standalone-file')
            path.write_bytes(b'image')
            with patch('audit_dc_worker_native.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='inspection error')):
                self.assertEqual(linkage(path)['status'],'inspection-failed')


if __name__=='__main__':unittest.main()
