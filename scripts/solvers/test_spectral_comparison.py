import unittest

from compare_spectral_plate import compare


def fixtures():
    material={'thickness_m':0.0002,'mu_initial':130,'saturation_polarization_t':0.25}
    def run(cells,modes,samples):
        return {'cells':cells,'modes':modes,'angle_samples':samples,'material':material.copy(),
                'geometry':{'pole_pitch':0.006,'pcb':0.0008,'gap':0.0005,'width':0.005,'height':0.003,'br':1.34},'pressure_pa':100,'field_ratio':1.3,
                'pressure_error':0,'field_ratio_error':0,'relative_gradient_residual':1e-12,
                'reflected_normal_modes_t':[0.01]*modes}
    names=['flex_0.2','flex_5','mnzn_2']
    baseline={'status':'comparison-only','failures':[],'cases':{name:{'runs':{'base':run(32,9,512),'depth':run(64,9,512),'modes':run(64,17,512)}} for name in names}}
    refined={'status':'comparison-only','failures':[],'cases':{name:{'runs':{'base':run(64,17,1024),'depth':run(128,17,1024),'modes':run(128,33,1024)}} for name in names}}
    for report in [baseline,refined]:report.update(analysis_sha256='a'*64,source_kernel_sha256='b'*64)
    refs=[{'status':'passed-subset','failures':[],'case':name,'material_input':material.copy(),
           'runs':{'domain':{'pressure_pa':100,'field_ratio':1.3}}} for name in names]
    return baseline,refined,refs


class SpectralComparisonTest(unittest.TestCase):
    def test_independent_refinements_and_references_pass(self):
        self.assertEqual(compare(*fixtures())[1],[])

    def test_material_geometry_or_unconverged_data_cannot_pass(self):
        for key,value in [('relative_gradient_residual',1e-6),('pressure_pa',float('nan')),
                          ('modes',9),('geometry',{'pcb':0.0016})]:
            a,b,refs=fixtures();b['cases']['flex_0.2']['runs']['modes'][key]=value
            with self.assertRaises(ValueError):compare(a,b,refs)
        a,b,refs=fixtures();refs[0]['material_input']['mu_initial']=145
        with self.assertRaises(ValueError):compare(a,b,refs)
        a,b,refs=fixtures();b['source_kernel_sha256']='c'*64
        with self.assertRaises(ValueError):compare(a,b,refs)

    def test_independent_fem_error_is_checked_without_rescaling(self):
        a,b,refs=fixtures();refs[0]['runs']['domain']['pressure_pa']=110
        self.assertTrue(any('independent FEM' in item for item in compare(a,b,refs)[1]))


if __name__=='__main__':
    unittest.main()
