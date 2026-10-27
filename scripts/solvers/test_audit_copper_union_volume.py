import unittest

import numpy as np

from audit_copper_union_volume import piece_volume,union_estimate


def disc(x,radius,inner=0.):
    return dict(kind='annulus',centre=np.array([x,0.]),radii=(inner,radius),z=(0.,1.),label=f'disc:{x}')


class DeclaredUnionVolumeTest(unittest.TestCase):
    def test_overlap_is_counted_once_and_drills_remove_material(self):
        a=dict(kind='segment',a=np.array([0.,0.]),b=np.array([2.,0.]),half_width=.5,z=(0.,1.),label='s')
        b=dict(kind='segment',a=np.array([1.,0.]),b=np.array([3.,0.]),half_width=.5,z=(0.,1.),label='t')
        estimate,error=union_estimate([a,b],[],20000)
        self.assertAlmostEqual(estimate,3.,delta=4*error+1e-12)
        self.assertEqual(piece_volume(a)+piece_volume(b),4.)
        drilled,error=union_estimate([disc(0.,1.)],[disc(0.,.5)],20000)
        self.assertAlmostEqual(drilled,np.pi*.75,delta=4*error+1e-3)

    def test_identical_primitives_do_not_inflate_union(self):
        estimate,error=union_estimate([disc(0.,1.),disc(0.,1.),disc(.5,1.)],[],20000)
        exact=2*np.arccos(.25)-.5*np.sqrt(1-.0625)
        self.assertAlmostEqual(estimate,2*np.pi-exact,delta=4*error+1e-3)
