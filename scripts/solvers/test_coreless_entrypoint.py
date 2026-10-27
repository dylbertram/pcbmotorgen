"""Production Rust JSON entrypoint checks, not a duplicate Python validator.

Build housing_motion_dump, then set PCB_MOTOR_HOUSING_BINARY for this suite.
The complete local helper run supplies it explicitly so nothing is skipped.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_housing_motion_reference import case_base


@unittest.skipUnless(os.environ.get('PCB_MOTOR_HOUSING_BINARY'),'built Rust housing entrypoint required')
class CorelessEntrypointTest(unittest.TestCase):
    def invoke(self,case):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.json';path.write_text(json.dumps(case,allow_nan=False));before=path.read_bytes()
            result=subprocess.run([os.environ['PCB_MOTOR_HOUSING_BINARY'],str(path)],capture_output=True,text=True,timeout=30)
            self.assertEqual(before,path.read_bytes(),'validation must not rewrite saved inputs')
            return result

    def test_rejects_each_out_of_bounds_request_without_numerical_fallback(self):
        bad=[]
        case=case_base();case['sim']['magnet_count']=13;bad.append(case)
        case=case_base();case['sim'].update(num_layers=18,max_layers=18);bad.append(case)
        case=case_base();case['sim']['backplane']['layers']=[{'material':'fr4','thickness_m':.0001}]*4;bad.append(case)
        case=case_base();case['sim']['backplane']['layers']=[{'material':'flex_ferrite','thickness_m':.002001}];bad.append(case)
        for key,value in [('thickness_m',.005001),('gap_m',.010001),('material','steel1018'),('material','stainless430')]:
            case=case_base();case['sim']['backplane']['housing'][key]=value;bad.append(case)
        case=case_base();case['geometry_hints']={'layer_z_m':[0.,-.0004,-.0008]};bad.append(case)
        for case in bad:
            with self.subTest(case=case):
                result=self.invoke(case);self.assertNotEqual(result.returncode,0)
                self.assertNotIn('"estimate"',result.stdout)

    def test_accepts_exact_maximum_bounds_and_preserves_input_bytes(self):
        case=case_base();case['sim'].update(magnet_count=12,num_layers=16,max_layers=16)
        case['sim']['backplane']['layers']=[{'material':'fr4','thickness_m':.002}]*3
        case['sim']['backplane']['housing'].update(material='stainless316',thickness_m=.005,gap_m=.01)
        result=self.invoke(case);self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);self.assertEqual(report['status'],'experimental')
        self.assertGreater(report['estimate']['housing_joule_power_w'],0.)

    def test_invalid_motion_profile_returns_explicit_unavailable_not_zero_heat(self):
        for duration in [0.,-1.]:
            case=case_base();case['duration_s']=duration;result=self.invoke(case)
            self.assertNotEqual(result.returncode,0);report=json.loads(result.stdout)
            self.assertEqual(report['status'],'unavailable');self.assertNotIn('estimate',report)

    def test_temperature_is_not_fabricated_without_thermal_assumptions(self):
        report=json.loads(self.invoke(case_base()).stdout)
        self.assertFalse(any('temperature' in key for key in report['estimate']))
        self.assertTrue(any('thermal model' in text for text in report['estimate']['warnings']))
