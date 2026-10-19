import copy
import tempfile
import unittest
from pathlib import Path

import magpylib as magpy
import numpy as np

from project_symmetry import quarter_model,quarter_geometry,mirrored_sample,validate_quarter_mesh


def model():
    return {'magnets':[{'name':f'm{i}','tag':i+2,'origin_m':[i*0.006-0.0145,-0.0025,0.0013],
                        'size_m':[0.005,0.005,0.003],'polarization_t':[0,0,1.34*(-1)**i]} for i in range(5)],
            'stack':[{'name':'plate','tag':7,'origin_m':[-0.018,-0.006,-0.0002],
                      'size_m':[0.036,0.012,0.0002],'mu_r':130,'bsat_t':0.25,'material':'flex_ferrite'}]}


class QuarterSymmetryTest(unittest.TestCase):
    def test_mesh_symmetry_tags_must_be_actual_planes_not_just_cad_labels(self):
        text='$Nodes\n4\n1 0 0 0\n2 0 1 0\n3 0 0 1\n4 1 0 0\n$EndNodes\n$Elements\n2\n1 2 2 1002 1 1 2 3\n2 2 2 1003 2 1 4 3\n$EndElements\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'quarter.msh';path.write_text(text)
            self.assertEqual(validate_quarter_mesh(path),{'symmetry_x_nodes':3,'symmetry_y_nodes':3})
            path.write_text(text.replace('1002 1 1 2 3','1002 1 1 4 3'))
            with self.assertRaises(ValueError):validate_quarter_mesh(path)

    def test_quarter_clips_only_a_verified_symmetry_and_preserves_input(self):
        original=model();before=copy.deepcopy(original);quarter=quarter_model(original)
        self.assertEqual(original,before)
        self.assertEqual(len(quarter['magnets']),3)
        self.assertTrue(all(o['origin_m'][0]>=0 and o['origin_m'][1]>=0 for o in quarter['magnets']+quarter['stack']))
        for group in ['magnets','stack']:
            self.assertAlmostEqual(sum(np.prod(o['size_m']) for o in quarter[group])*4/sum(np.prod(o['size_m']) for o in original[group]),1)
        invalid=model();invalid['magnets'][0]['polarization_t'][2]*=-1
        with self.assertRaises(ValueError):quarter_model(invalid)
        invalid=model();invalid['magnets'][2]['origin_m'][1]+=0.001
        with self.assertRaises(ValueError):quarter_model(invalid)

    def test_air_cut_keeps_planes_out_of_dirichlet_boundary(self):
        geo=quarter_geometry(quarter_model(model()),0.0008,0.0001,0.06)
        self.assertIn('Volume{quarter[]}',geo)
        self.assertIn('outer[]-={symx[i],-symx[i]}',geo)
        self.assertIn('outer[]-={symy[i],-symy[i]}',geo)
        self.assertIn('Physical Surface("symmetry_x",1002)',geo)

    def test_reflection_signs_agree_with_independent_full_magpylib_array(self):
        objects=model()['magnets']
        magnets=[magpy.magnet.Cuboid(dimension=o['size_m'],polarization=o['polarization_t'],
                                   position=np.asarray(o['origin_m'])+np.asarray(o['size_m'])/2) for o in objects]
        points=np.array([[-0.01,-0.003,0.0008],[-0.004,0.002,0.0008],[0.004,-0.002,0.0008],[0,0,0.0008]])
        before=points.copy()
        def reader(path,observations,name):return sum(m.getB(observations) for m in magnets)
        expected=reader(None,points,None)
        np.testing.assert_allclose(mirrored_sample(None,points,reader=reader),expected,atol=1e-15,rtol=1e-12)
        np.testing.assert_array_equal(points,before)


if __name__=='__main__':unittest.main()
