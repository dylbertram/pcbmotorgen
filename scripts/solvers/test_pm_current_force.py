import math
import unittest

import numpy as np
from numpy.polynomial.legendre import leggauss

from pm_current_force import MU0,array_force,biot_z,numerical_face_force
from reduced_potential import source_field


def square_loop(n=16):
    vertices=np.array([[-.006,-.006,0],[.006,-.006,0],[.006,.006,0],[-.006,.006,0],[-.006,-.006,0]])
    g,w=leggauss(n);points=[];vectors=[]
    for a,b in zip(vertices,vertices[1:]):
        points.extend(a+(g[:,None]+1)/2*(b-a));vectors.extend(w[:,None]/2*(b-a))
    return np.asarray(points),np.asarray(vectors)


class PMCurrentForceTest(unittest.TestCase):
    def setUp(self):
        self.magnet={'origin_m':[.001,-.001,.005],'size_m':[.002,.002,.002],'polarization_t':[0,0,1.]}

    def test_biot_savart_square_loop_axis_matches_exact_field(self):
        points,weights=square_loop(24);a=.006;z=.003
        exact=2*MU0*a*a/(math.pi*(a*a+z*z)*math.sqrt(2*a*a+z*z))
        self.assertAlmostEqual(biot_z(np.array([[0.,0.,z]]),points,weights)[0]/exact,1.,places=10)

    def test_analytic_pm_faces_match_independent_gauss_integration(self):
        points,weights=square_loop()
        exact=array_force([self.magnet],points,weights)[0]
        numerical=numerical_face_force(self.magnet,points,weights,12)
        np.testing.assert_allclose(exact,numerical,rtol=1e-8,atol=1e-14)

    def test_closed_loop_reciprocity_is_not_enforced_for_open_currents(self):
        points,weights=square_loop(24)
        field=source_field({'magnets':[self.magnet]})(points)
        conductor=np.cross(weights,field).sum(axis=0)
        mover=array_force([self.magnet],points,weights)[0]
        self.assertLess(np.linalg.norm(conductor+mover)/np.linalg.norm(mover),1e-8)
        # Deliberately nonclosed current: the independent operators must expose
        # rather than automatically cancel this continuity error.
        bad=array_force([self.magnet],points[:24],weights[:24])[0]
        other=np.cross(weights[:24],field[:24]).sum(axis=0)
        self.assertGreater(np.linalg.norm(other+bad)/max(np.linalg.norm(bad),1e-30),.02)
