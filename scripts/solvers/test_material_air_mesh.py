import unittest
import importlib.util

import numpy as np

from ngsolve_material_air_static import air_bounds,mesh_with_local_air


class LocalAirBoundsTest(unittest.TestCase):
    def test_mesh_partition_covers_sources_and_material_bodies(self):
        model={'magnets':[{'origin_m':[-.01,-.002,.001],'size_m':[.02,.004,.003]}],
            'stack':[{'name':'ferrite','mu_r':130.,'origin_m':[-.018,-.006,-.0002],'size_m':[.036,.012,.0002]}]}
        low,high=air_bounds(model,.002,.04)
        np.testing.assert_allclose(low,[-.02,-.008,-.0022]);np.testing.assert_allclose(high,[.02,.008,.006])
        with self.assertRaisesRegex(ValueError,'fit strictly'):air_bounds(model,.002,.02)
        with self.assertRaisesRegex(ValueError,'Positive finite'):air_bounds(model,float('nan'),.04)

    @unittest.skipUnless(importlib.util.find_spec('ngsolve'),'optional pinned NGSolve environment required')
    def test_partition_retains_exact_material_volumes_and_only_remote_boundary(self):
        import ngsolve as ng
        model={'magnets':[{'origin_m':[-.001,-.001,.001],'size_m':[.002,.002,.002]}],
            'stack':[{'name':'fer','mu_r':130.,'origin_m':[-.003,-.002,-.0002],'size_m':[.006,.004,.0002]},
                {'name':'housing','mu_r':1.,'origin_m':[-.003,-.002,-.0015],'size_m':[.006,.004,.0005]}]}
        mesh,metadata=mesh_with_local_air(ng,model,.001,.001,.01,.004,.0015,.001)
        for layer,region in zip(model['stack'],['fer','conductor']):
            actual=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,definedon=mesh.Materials(region),order=4))
            self.assertAlmostEqual(actual/np.prod(layer['size_m']),1.,places=10)
        self.assertEqual(list(mesh.GetMaterials()).count('air'),2)
        self.assertIn('outer',mesh.GetBoundaries());self.assertIn('near_air_interface',mesh.GetBoundaries())
        self.assertEqual(metadata['physical_effect'],'none; internal vacuum mesh partition, no Dirichlet condition')
