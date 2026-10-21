import unittest

from finite_current_zero_bias import magnetic_regions


class ZeroBiasMaterialTagTest(unittest.TestCase):
    def test_vacuum_control_keeps_former_ferrite_in_vacuum_energy_domain(self):
        model = {'stack': [{'name': 'ferrite', 'mu_r': 1.}, {'name': 'housing', 'mu_r': 1.}]}
        self.assertEqual(magnetic_regions(model, ['air', 'ferrite', 'housing']), [])
        model['stack'][0]['mu_r'] = 130.
        self.assertEqual([x['name'] for x in magnetic_regions(model, ['air', 'ferrite', 'housing'])], ['ferrite'])

    def test_missing_or_duplicate_interfaces_and_unsupported_housing_fail(self):
        model = {'stack': [{'name': 'ferrite', 'mu_r': 130.}, {'name': 'housing', 'mu_r': 1.}]}
        with self.assertRaises(ValueError):
            magnetic_regions(model, ['air', 'housing'])
        model['stack'][1]['mu_r'] = 1.02
        with self.assertRaises(ValueError):
            magnetic_regions(model, ['air', 'ferrite', 'housing'])


if __name__ == '__main__':
    unittest.main()
