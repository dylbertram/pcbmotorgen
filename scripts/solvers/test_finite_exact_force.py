import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from post_finite_exact_force import main


class FiniteExactInputTest(unittest.TestCase):
    def test_failed_source_or_incomplete_export_cannot_be_rescued(self):
        for source_status,report_status in [('failed','comparison-only'),('comparison-only','running')]:
            with self.subTest(source_status=source_status,report_status=report_status),tempfile.TemporaryDirectory() as directory:
                work=Path(directory);source=work/'summary.json';field=work/'field.json';output=work/'audit.json'
                source.write_text(json.dumps({'status':source_status,'failures':[]}));field.write_text(json.dumps({'status':report_status}))
                with patch('sys.argv',['audit','--work',str(work),'--field-report',str(field),'--output',str(output)]):
                    with self.assertRaisesRegex(ValueError,'completed original'):main()
                self.assertFalse(output.exists())

    def test_wrong_summary_or_smoothed_elmer_field_is_rejected(self):
        for digest,representation,message in [('wrong','element','different original solve'),(None,'nodal','nodal smoothing')]:
            with self.subTest(representation=representation),tempfile.TemporaryDirectory() as directory:
                work=Path(directory);source=work/'summary.json';field=work/'field.json';output=work/'audit.json'
                source.write_text(json.dumps({'status':'comparison-only','failures':[],'request':{'backend':'elmer'}}))
                field.write_text(json.dumps({'status':'comparison-only','source_summary_sha256':digest or hashlib.sha256(source.read_bytes()).hexdigest(),
                                             'field_representation':representation}))
                with patch('sys.argv',['audit','--work',str(work),'--field-report',str(field),'--output',str(output)]):
                    with self.assertRaisesRegex(ValueError,message):main()
                self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
