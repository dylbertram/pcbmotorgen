import sys
import unittest

from pathlib import Path
from preflight_linear_dc_campaign import output_paths,probe,schedule_budgets


class ActualCliPreflightTest(unittest.TestCase):
    def test_section_work_is_input_not_a_second_writer_to_its_source(self):
        self.assertEqual(output_paths(dict(work='/actual-source',output='/fresh-sections.json')),[Path('/fresh-sections.json')])
        self.assertEqual(output_paths(dict(work='/fresh-source')),[Path('/fresh-source')])

    def test_real_section_parser_rejects_the_historical_wrong_flags_without_running_audit(self):
        wrong=['audit_dc_section_refinement.py','--first-work','/not-read/a','--second-work','/not-read/b',
            '--first-sections','/not-read/a.json','--second-sections','/not-read/b.json','--output','/never-written.json','--kind','mesh']
        with self.assertRaisesRegex(ValueError,'CLI parser rejected'):probe(sys.executable,wrong)
        correct=[v.replace('--first-sections','--first-report').replace('--second-sections','--second-report') for v in wrong]
        parsed,digest=probe(sys.executable,correct)
        self.assertEqual(parsed['first_report'],'/not-read/a.json');self.assertEqual(len(digest),64)

    def test_source_entry_stops_before_reading_inputs_or_initializing_ngsolve_tasks(self):
        parsed,_=probe(sys.executable,['solve_linear_dc_study.py','--geometry-work','/not-read','--matrix','/not-read.json',
            '--work','/never-created','--mesh','.0002','--curvature-safety','6','--port-fraction','.4','--max-dofs','24000000','--threads','2'])
        self.assertEqual(parsed['port_fraction'],.4);self.assertEqual(parsed['threads'],2)

    def test_full_timeout_schedule_respects_global_memory_and_dependencies(self):
        job=lambda n,t,m,d=():dict(name=n,timeout_s=t,memory_gib=m,depends=list(d))
        spec=dict(max_parallel=3,memory_budget_gib=17,jobs=[job('source',100,13),job('large-cache',200,5,['source']),
            job('cache2',150,5,['source']),job('cache3',100,5,['source']),job('force',50,3,['large-cache','cache2','cache3'])])
        result=schedule_budgets(spec)
        times={j['name']:j for j in result['timeline']}
        self.assertEqual(times['large-cache']['start_s'],130)
        self.assertGreaterEqual(times['force']['start_s'],times['large-cache']['end_s'])
        for at in [0,130,200,350,360]:
            active=[j for j in result['timeline'] if j['start_s']<=at<j['end_s']]
            self.assertLessEqual(sum(j['memory_gib'] for j in active),17);self.assertLessEqual(len(active),3)
        self.assertEqual(result['declared_order_budget_makespan_s'],440)
