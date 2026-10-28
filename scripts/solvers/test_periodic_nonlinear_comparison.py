import unittest

from compare_periodic_nonlinear import observable


class NonlinearPeriodicObservableTest(unittest.TestCase):
    def test_nonpassive_or_nonfinite_trials_cannot_enter_agreement(self):
        for reflection,loss in [([.1,0.],0.),([float('nan'),0.],1.)]:
            with self.assertRaises(ValueError):observable(reflection,loss)

    def test_reflection_is_converted_to_the_same_declared_sheet_observable(self):
        coil,loss=observable([.1,-.02],5.)
        self.assertEqual(coil.shape,(1,2));self.assertEqual(loss.shape,(1,))
        self.assertGreater(coil[0,0],1.);self.assertLess(coil[0,1],0.)
