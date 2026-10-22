from copy import deepcopy
import json
from pathlib import Path
import unittest

from plan_linear_dc_source_force_campaign import plan


class SourceForceCampaignPlanTest(unittest.TestCase):
    def spec(self):
        return json.loads(Path(__file__).with_name('cases').joinpath('linear-dc-day-case-a-source-force-controls-20261022.json').read_text())

    def test_preflight_stage_never_launches_full_cache_or_coupling(self):
        campaign,_=plan(self.spec(),Path('/actual'),1,'2026-10-22T18:29:49Z')
        self.assertEqual(len(campaign['jobs']),15)
        self.assertFalse(any('--max-cache-seconds' in j['args'] or j['args'][0]=='finite_current_coupling.py' for j in campaign['jobs']))
        self.assertTrue(all(j['memory_gib']<=1.3 for j in campaign['jobs']))

    def test_all_three_isolated_sources_get_fresh_complete_current_pose_solves(self):
        campaign,audit=plan(self.spec(),Path('/actual'),2,'2026-10-22T18:29:49Z')
        self.assertEqual(set(audit['variants']),{'mesh','port','curvature'})
        coupled=[j for j in campaign['jobs'] if j['args'][0]=='finite_current_coupling.py']
        self.assertEqual(len(coupled),9);self.assertTrue(all(not j.get('prior') for j in coupled))
        self.assertEqual(sum(bool(j.get('prior')) for j in campaign['jobs']),15)
        for kind,variant in audit['variants'].items():
            self.assertEqual(set(variant['jobs']),{'nominal','plus100um','minus100um'})
            self.assertTrue(all(kind+'-' in path for path in variant['jobs'].values()))
        self.assertEqual(campaign['memory_budget_gib'],4.)

    def test_changed_magnetic_discretization_cannot_hide_in_source_control(self):
        spec=deepcopy(self.spec());spec['magnetic_controls']['degree']=10
        with self.assertRaisesRegex(ValueError,'unchanged'):plan(spec,Path('/actual'),2,'2026-10-22T18:29:49Z')
