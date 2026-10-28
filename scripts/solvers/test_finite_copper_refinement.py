import copy
import unittest

from finite_copper_refinement import refined_inputs


class IsolatedRefinementInputsTest(unittest.TestCase):
    def source(self):
        return dict(request=dict(mesh_m=.0004,port_fraction=.5,geometry_order=1,iterative=True,curvature_safety=4.),
            geometry=dict(drive_path_m=[[0.,0.,0.],[1.,0.,0.]],drive_volume_m3=.1,volume_m3=1.,return_width_m=.01))

    def test_spatial_refinement_does_not_change_physical_copper_or_port(self):
        source=self.source();original=copy.deepcopy(source);request,geometry=refined_inputs(source,'mesh',.0003)
        self.assertEqual(geometry,source['geometry']);self.assertEqual(request['curvature_safety'],4.)
        self.assertEqual(request['mesh_m'],.0003);self.assertEqual(source,original)

    def test_port_repartition_preserves_union_and_unit_emf_geometry(self):
        source=self.source();request,geometry=refined_inputs(source,'port',.4)
        self.assertEqual(request['mesh_m'],.0004);self.assertEqual(request['curvature_safety'],4.)
        self.assertAlmostEqual(geometry['drive_path_m'][0][0],.1);self.assertAlmostEqual(geometry['drive_path_m'][1][0],.9)
        self.assertAlmostEqual(geometry['drive_volume_m3'],.08);self.assertEqual(geometry['volume_m3'],1.)
        for kind,value in [('mesh',.0004),('mesh',.0005),('port',.5),('port',1.),('port',0.),('mesh',float('nan'))]:
            with self.subTest(kind=kind,value=value),self.assertRaises(ValueError):refined_inputs(source,kind,value)
