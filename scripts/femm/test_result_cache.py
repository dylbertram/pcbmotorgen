import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import femm_backplane as femm


CASE={'name':'job','bands':[],'rects':[{'group':1}],'labels':[],'lines':[],'points':[]}
COMPLETE='AJ_sources_re 1\nAJ_sources_im 0\nenergy_total 0.5\n'


class ResultCacheTest(unittest.TestCase):
    def test_failed_process_cannot_leave_a_reusable_even_complete_output(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);out=work/'job.out'
            def fail(*args,**kwargs):
                out.write_text(COMPLETE)
                raise subprocess.CalledProcessError(124,args[0])
            with patch('femm_backplane.subprocess.run',side_effect=fail):
                with self.assertRaises(subprocess.CalledProcessError):femm.run_femm(CASE,work)
            self.assertFalse(out.exists())
            self.assertEqual(len(list(work.glob('job.out.incomplete.*'))),1)
            self.assertEqual(json.loads((work/'job.receipt.json').read_text())['status'],'timeout')
            def success(*args,**kwargs):out.write_text(COMPLETE)
            with patch('femm_backplane.subprocess.run',side_effect=success) as process:
                self.assertEqual(femm.run_femm(CASE,work)['AJ_sources_re'],1)
                femm.run_femm(CASE,work)
                self.assertEqual(process.call_count,1)
            self.assertEqual(json.loads((work/'job.receipt.json').read_text())['status'],'completed')

    def test_legacy_complete_output_is_not_given_a_fabricated_exit_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            (work/'job.case.lua').write_text('case = '+femm.lua(CASE)+'\n')
            (work/'job.out').write_text(COMPLETE)
            with patch('femm_backplane.subprocess.run') as process:
                femm.run_femm(CASE,work)
                process.assert_not_called()
            self.assertFalse((work/'job.receipt.json').exists())
            (work/'job.receipt.json').write_text(json.dumps({'status':'failed','exit_code':1}))
            with self.assertRaises(ValueError):femm.cached_femm_result(CASE,work)

    def test_partial_legacy_or_changed_committed_output_is_not_a_cache_hit(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);out=work/'job.out'
            (work/'job.case.lua').write_text('case = '+femm.lua(CASE)+'\n')
            out.write_text('AJ_sources_re 999\n')
            def success(*args,**kwargs):out.write_text(COMPLETE)
            with patch('femm_backplane.subprocess.run',side_effect=success) as process:
                femm.run_femm(CASE,work)
                out.write_text(COMPLETE.replace('re 1','re 2'))
                femm.run_femm(CASE,work)
                self.assertEqual(process.call_count,2)
            self.assertGreaterEqual(len(list(work.glob('job.out.previous.*'))),2)

    def test_nonfinite_or_missing_requested_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.out'
            for text in ['AJ_sources_re nan\nAJ_sources_im 0\nenergy_total 1\n', 'AJ_sources_re 1\n']:
                path.write_text(text)
                with self.assertRaises(ValueError):femm.parse_femm_result(CASE,path)


if __name__=='__main__':
    unittest.main()
