import unittest

from run_linear_dc_campaign import validate_campaign


def spec(**changes):
    value=dict(schema='linear-dc-campaign-v1',max_parallel=2,memory_budget_gib=8,
        jobs=[dict(name='a',log='a.log',memory_gib=2),dict(name='b',log='b.log',memory_gib=2,depends=['a'])])
    value.update(changes);return value


class DeclaredCampaignTest(unittest.TestCase):
    def test_dependencies_must_be_declared_before_use(self):
        validate_campaign(spec())
        with self.assertRaisesRegex(ValueError,'earlier'):validate_campaign(spec(jobs=list(reversed(spec()['jobs']))))

    def test_duplicate_names_logs_and_oversized_jobs_are_refused(self):
        with self.assertRaisesRegex(ValueError,'names'):validate_campaign(spec(jobs=[dict(name='a',log='a.log',memory_gib=1)]*2))
        with self.assertRaisesRegex(ValueError,'logs'):validate_campaign(spec(jobs=[dict(name='a',log='x.log',memory_gib=1),dict(name='b',log='x.log',memory_gib=1)]))
        with self.assertRaisesRegex(ValueError,'memory'):validate_campaign(spec(jobs=[dict(name='a',log='a.log',memory_gib=9)]))
        with self.assertRaisesRegex(ValueError,'Bounded'):validate_campaign(spec(memory_budget_gib=20))
