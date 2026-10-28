import unittest

import numpy as np

from audit_exterior_current_field import observation_points


class ExteriorPointSelectionTest(unittest.TestCase):
    def test_actual_trace_selection_is_order_independent_and_below_whole_source(self):
        sections=[dict(label='trace:C:2',centre_m=[2.,3.,-.0048]),dict(label='trace:A:1',centre_m=[0.,1.,-.0048]),
            dict(label='via:A:2',centre_m=[5.,5.,-.005]),dict(label='trace:A:0',centre_m=[9.,9.,0.])]
        points,labels=observation_points(sections,-.004835)
        np.testing.assert_allclose(points,[[0.,1.,-.005835],[2.,3.,-.006835]])
        self.assertEqual(labels,['trace:A:1','trace:C:2'])
        np.testing.assert_array_equal(points,observation_points(list(reversed(sections)),-.004835)[0])
        with self.assertRaises(ValueError):observation_points([],-.005)
