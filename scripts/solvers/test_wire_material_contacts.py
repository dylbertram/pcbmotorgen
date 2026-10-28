import unittest

from wire_material_contacts import contacts


class WireMaterialContactTest(unittest.TestCase):
    def test_boundary_interior_crossing_and_endpoint_contacts_are_distinct(self):
        model={'stack':[{'name':'fer','mu_r':130.,'origin_m':[0.,0.,0.],'size_m':[1.,1.,1.]}]}
        segments=[[[-1.,.5,1.],[2.,.5,1.]],[[-1.,.5,.5],[2.,.5,.5]],[[-1.,.5,.5],[0.,.5,.5]],[[-1.,.5,2.],[2.,.5,2.]]]
        result=contacts(segments,[1.,2.,1.,1.],model)['fer']
        self.assertEqual(result['boundary_segments'],1);self.assertEqual(result['interior_segments'],1);self.assertEqual(result['point_contacts'],1)
        self.assertAlmostEqual(result['boundary_length_m'],1.);self.assertAlmostEqual(result['interior_length_m'],1.)
        self.assertAlmostEqual(result['interior_abs_current_length_a_m'],2.)

    def test_zero_current_does_not_create_a_source_contact(self):
        model={'stack':[{'name':'fer','mu_r':130.,'origin_m':[0.,0.,0.],'size_m':[1.,1.,1.]}]}
        result=contacts([[[0.,.5,1.],[1.,.5,1.]]],[0.],model)['fer']
        self.assertEqual(result['boundary_length_m'],0.)
