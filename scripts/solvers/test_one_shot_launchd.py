from pathlib import Path
import tempfile
import unittest

from one_shot_launchd import job_spec


class OneShotOwnershipTest(unittest.TestCase):
    def test_explicit_no_restart_and_no_login_install(self):
        with tempfile.TemporaryDirectory() as folder:
            value=job_spec('com.pcbmotorgen.dc.test',['/usr/bin/true'],folder,{'OMP_NUM_THREADS':'1'})
            self.assertIs(value['KeepAlive'],False);self.assertIs(value['RunAtLoad'],True)
            self.assertIs(value['AbandonProcessGroup'],False)
            self.assertEqual(Path(value['StandardOutPath']).parent,Path(folder).resolve())
            for label in ['other-user-service','com.pcbmotorgen.dc./outside']:
                with self.subTest(label=label),self.assertRaises(ValueError):job_spec(label,['/usr/bin/true'],folder)
