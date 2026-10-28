import copy
import re
import unittest

from magnet_mesh import with_magnet_faces
from mesh_stretch import stretched_geometry
from project_symmetry import quarter_model
from test_mesh_stretch import model


class MagnetMeshControlTest(unittest.TestCase):
    def test_explicit_physical_band_preserves_vertical_reach_after_stretch(self):
        physical=quarter_model(model())
        geometry=stretched_geometry(physical,0.0008,0.0001,0.03,4,quarter=True)
        refined=with_magnet_faces(geometry,physical,0.0002,4,0.005,0.0004)
        top=(physical['magnets'][0]['origin_m'][2]+physical['magnets'][0]['size_m'][2])*4
        self.assertTrue(any(abs(float(value)-top-0.0004*4)<1e-15 for value in re.findall(r'\.ZMax=([^;]+);',refined)))
        self.assertIn('.VIn=0.00020000000000000001;',refined)
        for bad in [0,-1,True,float('inf')]:
            with self.assertRaises(ValueError):with_magnet_faces(geometry,physical,0.0002,4,0.005,bad)

    def test_only_local_fields_and_minimum_change_not_physics_or_far_air(self):
        physical=quarter_model(model());before=copy.deepcopy(physical)
        geometry=stretched_geometry(physical,0.0008,0.0001,0.03,4,quarter=True)
        refined=with_magnet_faces(geometry,physical,0.0001,4,0.005)
        self.assertEqual(physical,before)
        for line in geometry.splitlines():
            if not line.startswith('Mesh.MeshSizeMin='):self.assertIn(line+'\n',refined)
        self.assertEqual(len(re.findall(r'^Field\[\d+\]=Box;$',refined,re.M))-len(re.findall(r'^Field\[\d+\]=Box;$',geometry,re.M)),4)
        self.assertTrue(any(abs(float(value)-0.0051)<1e-15 for value in re.findall(r'\.ZMin=([^;]+);',refined)))
        self.assertEqual(refined.count('Sphere(1)'),1)

    def test_existing_field_ids_do_not_collide_and_both_backgrounds_are_combined(self):
        physical=quarter_model(model());geometry=stretched_geometry(physical,0.0008,0.0001,0.03,4,quarter=True)
        refined=with_magnet_faces(geometry,physical,0.0001,4,0.005)
        ids=re.findall(r'^Field\[(\d+)\]=',refined,re.M)
        self.assertEqual(len(ids),len(set(ids)))
        previous=re.findall(r'^Background Field=(\d+);$',geometry,re.M)[0]
        self.assertRegex(refined,rf'FieldsList=\{{{previous},\d+')
        for bad in [0,float('nan'),True]:
            with self.assertRaises(ValueError):with_magnet_faces(geometry,physical,bad,4,0.005)
        with self.assertRaises(ValueError):with_magnet_faces('no mesh',physical,0.0001,4,0.005)
