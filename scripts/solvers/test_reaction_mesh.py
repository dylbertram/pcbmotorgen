import re
import unittest

from project_static import geometry
from reaction_mesh import with_observation_band
from reduced_potential import response_model
import test_project_static


class ReactionMeshTest(unittest.TestCase):
    def test_observation_band_preserves_source_bounds_and_physical_z_reach(self):
        model=test_project_static.ProjectStaticTest().model()
        reduced=response_model(model,False,True)
        original=geometry(reduced,.0008,.0001,.06)
        changed=with_observation_band(original,model,.0008,.001,4,.01)
        identifier=max(map(int,re.findall(r'^Field\[(\d+)\]=',original,re.M)))+10
        zmin=float(re.search(rf'Field\[{identifier}\]\.ZMin=([^;]+);',changed)[1])
        zmax=float(re.search(rf'Field\[{identifier}\]\.ZMax=([^;]+);',changed)[1])
        self.assertAlmostEqual(zmin,(.0021-.001)*4,places=15)
        self.assertAlmostEqual(zmax,(.0051+.001)*4,places=15)
        self.assertNotIn('Physical Volume("magnet_',changed)
        self.assertEqual(changed[:len(original)],original)

    def test_invalid_bands_and_implicit_geometry_are_rejected(self):
        model=test_project_static.ProjectStaticTest().model()
        with self.assertRaises(ValueError):with_observation_band('none',model,.001,.001,4,.01)
        for value in [0,float('nan'),True]:
            with self.assertRaises(ValueError):with_observation_band('none',model,.001,value,4,.01)
