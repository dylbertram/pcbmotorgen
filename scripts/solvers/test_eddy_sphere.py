import unittest

from eddy_sphere_reference import dipole_loss,volume_loss,weak_loss


class EddySphereReferenceTest(unittest.TestCase):
    def test_dipole_work_matches_independent_volume_integral(self):
        for frequency in [1.,1000.,5000.,100000.]:
            args=(.003,25e6,frequency,.01)
            power=dipole_loss(*args)
            self.assertGreater(power,0.)
            self.assertLess(abs(volume_loss(*args)/power-1),1e-9)

    def test_weak_limit_and_skin_shielding_are_not_confused(self):
        low=(.003,25e6,1.,.01);high=(.003,25e6,5000.,.01)
        self.assertLess(abs(dipole_loss(*low)/weak_loss(*low)-1),1e-5)
        self.assertLess(dipole_loss(*high)/weak_loss(*high),.9)
        with self.assertRaises(ValueError):dipole_loss(.003,-1,1,.01)
