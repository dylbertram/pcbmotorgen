import copy
import unittest

from compare_plate2d import compare


def report(backend):
    result={'reference':{'field_ratio':1.05,'pressure_pa':7200}, 'field_ratio':1.05,'pressure_pa':7200}
    for part in ['bare','plate']:
        result[part]={'sha256':{'plate2d.geo':'geometry','plate.msh':'mesh'}}
    return {'backend':backend,'status':'passed','refined':True,'failures':[],
            'cases':{'thin':{'fine':copy.deepcopy(result),'domain':copy.deepcopy(result)}}}


class ComparisonTest(unittest.TestCase):
    def test_matching_independent_jobs(self):
        a,b=report('elmer'),report('getdp')
        self.assertTrue(compare(a,b)['passed'])
        b['cases']['thin']['fine']['pressure_pa'] *= 1.1
        self.assertFalse(compare(a,b)['passed'])

    def test_incomplete_or_different_jobs_are_rejected(self):
        for change in [lambda b:b.update(status='running'),lambda b:b.update(refined=False),
                       lambda b:b.update(backend='elmer'),lambda b:b.update(failures=['failed']),
                       lambda b:b['cases']['thin']['fine']['bare']['sha256'].update({'plate.msh':'other'})]:
            a,b=report('elmer'),report('getdp')
            change(b)
            with self.assertRaises(ValueError):
                compare(a,b)


if __name__=='__main__':
    unittest.main()
