import unittest

import magpylib as magpy
import numpy as np

from maxwell_stress import box_faces,force


class ClosedSurfaceTest(unittest.TestCase):
    def test_uniform_field_exerts_no_net_force(self):
        faces = box_faces(0.006,-0.005,0.0006,16)
        b = [np.tile([0.1,0.2,0.3],(len(points),1)) for points,_,_ in faces]
        np.testing.assert_allclose(force(faces,b),0,atol=1e-14)
        with self.assertRaises(ValueError):
            force(faces,b[:-1])

    def test_external_pm_exerts_zero_force_on_empty_box_under_refinement(self):
        magnet=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028))
        errors=[]
        for n in [32,64,128]:
            faces=box_faces(0.0064,-0.0054,0.0004,n)
            result=force(faces,[magnet.getB(points) for points,_,_ in faces])
            errors.append(np.linalg.norm(result))
            np.testing.assert_allclose(result[:2],0,atol=1e-14)
        self.assertLess(errors[1],errors[0]/3)
        self.assertLess(errors[2],errors[1]/3)
        self.assertLess(errors[-1],1e-5)


if __name__=='__main__':
    unittest.main()
