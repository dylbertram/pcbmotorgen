import unittest

from prepare_linear_dc_copper import partition_checks,validate_copper_shape,closed_return


class ActualPartitionTest(unittest.TestCase):
    def test_empty_and_disconnected_copper_cannot_become_a_return_only_source(self):
        from types import SimpleNamespace
        for shape in [SimpleNamespace(mass=0.,solids=[]),SimpleNamespace(mass=float('nan'),solids=[1]),SimpleNamespace(mass=1.,solids=[1,2])]:
            with self.assertRaisesRegex(ValueError,'nonempty solid'):validate_copper_shape(shape)
            with self.assertRaisesRegex(ValueError,'nonempty solid'):closed_return(shape,{},[])

    def test_disjoint_actual_boxes_pass_and_overlap_is_not_repaired(self):
        from netgen.occ import Box,Pnt
        copper=Box(Pnt(0,0,.001),Pnt(.001,.001,.001035))
        model=dict(stack=[dict(name='shield',origin_m=[0.,0.,-.0002],size_m=[.001,.001,.0002])],magnets=[])
        checks=partition_checks(copper,copper,model)
        self.assertEqual(checks['winding:shield']['overlap_m3'],0.)
        self.assertAlmostEqual(checks['winding:shield']['minimum_brep_distance_m'],.001)
        model['stack'][0]['origin_m'][2]=.001
        with self.assertRaisesRegex(ValueError,'user decision'):partition_checks(copper,copper,model)
