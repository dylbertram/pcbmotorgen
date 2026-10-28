import unittest

import numpy as np
from numpy.polynomial.legendre import leggauss

from pm_current_force import magnetization_force,MU0


class MagnetizationForceTest(unittest.TestCase):
    def test_face_kernel_derivative_matches_independent_dipole_field_integration(self):
        magnet={'origin_m':[.001,-.001,.005],'size_m':[.002,.002,.002],'polarization_t':[0,0,1.]}
        points=np.array([[0.,0.,0.],[.003,.002,-.001]])
        moments=np.array([[.001,.002,.003],[-.001,.001,-.002]])
        direct=magnetization_force(magnet,points,moments,1e-7)
        n=16;nodes,w=leggauss(n);origin=np.array(magnet['origin_m']);size=np.array(magnet['size_m']);numerical=np.zeros(3)
        for axis in range(3):
            j,k=[i for i in range(3) if i!=axis]
            u,v=np.meshgrid((nodes+1)/2,(nodes+1)/2,indexing='ij');area=np.outer(w,w).ravel()*size[j]*size[k]/4
            for side in range(2):
                obs=np.tile(origin,(n*n,1));obs[:,axis]+=side*size[axis];obs[:,j]+=u.ravel()*size[j];obs[:,k]+=v.ravel()*size[k]
                d=obs[:,None,:]-points[None,:,:];squared=np.sum(d*d,axis=2)
                bz=np.sum((3*d[:,:,2]*np.sum(moments[None,:,:]*d,axis=2)/squared-moments[None,:,2])/(squared*np.sqrt(squared)),axis=1)*MU0/(4*np.pi)
                numerical[axis]+=(2*side-1)/MU0*float(area@bz)
        np.testing.assert_allclose(direct,numerical,rtol=1e-7,atol=1e-12)
        refined=magnetization_force(magnet,points,moments,5e-8)
        np.testing.assert_allclose(direct,refined,rtol=1e-7,atol=1e-12)
