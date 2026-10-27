import unittest

from compare_housing_model_scope import mapped_case


def record():
    return {'request':{'slot':0.,'sigma':25e6,'speed':20.},'profile':{'duration_s':.006},'excluded_materials':[{'material':'flex_ferrite'}],
        'housing':{'material':'aluminum6061','mu_r':1.,'origin_m':[-.018,-.006,-.0013],'size_m':[.036,.012,.001]},
        'model':{'pcb_thickness_m':.0008,'footprint_m':[.036,.012],
            'magnets':[{'origin_m':[i*.006-.0145,-.0025,.0013],'size_m':[.005,.005,.003],'polarization_t':[0,0,1.34*(-1)**i]} for i in range(5)]}}


class HousingModelScopeTest(unittest.TestCase):
    def test_maps_physical_separation_without_relocating_housing(self):
        source=record();case,mapping=mapped_case(source)
        self.assertAlmostEqual(case['sim']['backplane']['housing']['gap_m'],.0003)
        self.assertAlmostEqual(mapping['actual_pm_to_housing_surface_m'],.0016)
        self.assertEqual(case['sim']['backplane']['layers'],[])
        self.assertEqual(source['housing']['origin_m'],[-.018,-.006,-.0013])

    def test_rejects_physical_model_substitution(self):
        for mutate in [lambda r:r['request'].update(slot=.0005),lambda r:r['request'].update(sigma=1.35e6),
                lambda r:r['housing'].update(material='stainless316'),lambda r:r['model']['magnets'][1].update(polarization_t=[0,0,1.34])]:
            source=record();mutate(source)
            with self.assertRaises(ValueError):mapped_case(source)
