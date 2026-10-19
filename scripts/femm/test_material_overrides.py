import unittest

from femm_backplane import stack_bands, bh_points


class MaterialOverrideTest(unittest.TestCase):
    def test_mu_override_does_not_silently_disable_nonlinear_bh(self):
        layers=[{'material':'flex_ferrite','thickness_m':0.0002,'mu_r':145,'bsat_t':0.3}]
        bands,mats=stack_bands({'layers':layers,'housing':None},0,'knee')
        material=mats[0]
        self.assertEqual(material['mu'],145)
        self.assertEqual(material['bh'],bh_points(145,0.3,True))
        self.assertEqual(next(b for b in bands if b['group']==2)['mat'],material['name'])

    def test_null_overrides_retain_defaults_and_distinct_layers_do_not_collide(self):
        default={'material':'flex_ferrite','thickness_m':0.0002,'mu_r':None,'bsat_t':None}
        _,mats=stack_bands({'layers':[default],'housing':None},0,'knee')
        self.assertEqual(mats[0]['name'],'flex_ferrite')
        self.assertEqual(mats[0]['bh'],bh_points(130,0.25,True))
        layers=[dict(default,bsat_t=0.25),dict(default,bsat_t=0.3)]
        _,mats=stack_bands({'layers':layers,'housing':None},0,'knee')
        self.assertEqual(len(mats),2)
        self.assertNotEqual(mats[0]['name'],mats[1]['name'])
        self.assertNotEqual(mats[0]['bh'],mats[1]['bh'])


if __name__=='__main__':
    unittest.main()
