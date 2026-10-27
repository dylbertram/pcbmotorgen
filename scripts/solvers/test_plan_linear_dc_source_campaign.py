import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from run_linear_dc_campaign import validate_campaign


class SourceCampaignGateTest(unittest.TestCase):
    def test_refinements_wait_for_actual_baseline_local_and_independent_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);matrix=root/'matrix.json';output=root/'campaign.json'
            matrix.write_text(json.dumps(dict(source_controls=dict(mesh_m=[.0002,.00015],curvature_safety=[4.,6.],port_fraction=[.5,.4]))))
            subprocess.run([sys.executable,str(Path(__file__).with_name('plan_linear_dc_source_campaign.py')),
                '--prefix','test-','--copper-work',str(root/'copper'),'--matrix',str(matrix),'--output',str(output),
                '--cutoff','2026-10-22T18:29:49.742086Z','--basis-curvature','6','--resistivity','2e-8','--declared-no-stubs'],check=True,capture_output=True)
            spec=json.loads(output.read_text());validate_campaign(spec)
            self.assertEqual(spec['max_parallel'],1)
            jobs={job['name']:job for job in spec['jobs']};basis='source-m200-c6-p50'
            self.assertEqual(next(iter(jobs)),basis);self.assertEqual(jobs[basis]['depends'],[])
            required={'active-m200-c6-p50','passive-basis','return-basis','agreement-basis'}
            for name,job in jobs.items():
                if name.startswith('source-') and name!=basis or name=='rt0-basis':
                    self.assertEqual(set(job['depends']),required)
            self.assertIn('--declared-no-stubs',jobs['passive-basis']['args'])
            self.assertIn('agreement',jobs['agreement-basis']['args'])
