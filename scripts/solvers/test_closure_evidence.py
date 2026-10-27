import json
import tempfile
import unittest
from pathlib import Path

from audit_current_closure import load


class ClosureEvidenceTest(unittest.TestCase):
    def test_missing_failed_or_mismatched_receipt_cannot_qualify_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);summary=work/'summary.json';receipt=work/'receipt.json'
            report={'status':'passed-finite-current-closure-low-rm-source-only','failures':[],
                'magnetic_reynolds_number':.001,'sigma_s_m':25e6,'speed_m_s':.001,'source_snapshots':{}}
            summary.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'receipt'):load(work)
            report['command_receipt']=str(receipt);summary.write_text(json.dumps(report))
            command=['python','finite_current_closure.py','--work',str(work),'--sigma','25000000','--speed','.001']
            successful={'status':'completed','exit_code':0,'command':command}
            receipt.write_text(json.dumps(successful));self.assertEqual(load(work)['speed_m_s'],.001)
            for bad in [dict(successful,status='timeout'),dict(successful,exit_code=1),
                dict(successful,command=command[:-1]+['20']),dict(successful,command=['--work',str(work/'other')])]:
                receipt.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):load(work)
