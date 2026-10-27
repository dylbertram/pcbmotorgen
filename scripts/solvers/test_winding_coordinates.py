import copy
import unittest

import numpy as np

from winding_coordinates import translation,translate_samples


class WindingCoordinatesTest(unittest.TestCase):
    def setUp(self):
        self.sim=dict(magnet_count=5,magnet_pitch_m=.006,magnet_remanence_t=1.34,
            pcb_thickness_m=.0008,board_width_m=.008,magnet_dims_m=[.005,.005,.003],air_gap_m=.0005)
        self.model=dict(array_centre_mm=[2.,-1.],pcb_thickness_m=.0008,magnets=[
            dict(origin_m=[.002+(i-2)*.006-.0025,-.001-.0025,.0013],
                 size_m=[.005,.005,.003],polarization_t=[0,0,1.34*(-1)**i]) for i in range(5)])

    def test_mover_translation_applied_exactly_once(self):
        shift=translation(self.sim,self.model,.0414)
        np.testing.assert_allclose(shift,[-.0514,-.005,.0008],atol=1e-15)
        first_source_centre=np.array([.0414,.004,0.])+shift
        np.testing.assert_allclose(first_source_centre,[-.010,-.001,.0008],atol=1e-15)

    def test_signed_vias_and_imported_physical_depths_are_preserved(self):
        points=np.array([[.01,.002,0.],[.02,.003,-.0008],[.03,.004,-.0004]])
        dl=np.array([[.001,0.,0.],[0.,-.001,0.],[0.,0.,-.0008]])
        mapped,directions=translate_samples(points,dl,self.sim,self.model,.0414)
        np.testing.assert_array_equal(directions,dl)
        np.testing.assert_allclose(np.diff(mapped,axis=0),np.diff(points,axis=0),atol=1e-15)
        np.testing.assert_allclose(mapped[:,2],[.0008,0.,.0004],atol=1e-15)
        self.assertFalse(np.shares_memory(mapped,points));self.assertFalse(np.shares_memory(directions,dl))

    def test_rejects_the_old_thicker_board_and_changed_source(self):
        with self.assertRaisesRegex(ValueError,'PCB thickness'):
            translation(dict(self.sim,pcb_thickness_m=.0016),self.model,0.)
        for name in ['origin_m','size_m','polarization_t']:
            changed=copy.deepcopy(self.model);changed['magnets'][0][name][0]+=.001
            with self.assertRaises(ValueError):translation(self.sim,changed,0.)

    def test_translation_matches_independent_analytical_source(self):
        import magpylib as magpy
        def magnets(origins):
            return magpy.Collection(*[magpy.magnet.Cuboid(dimension=m['size_m'],polarization=m['polarization_t'],
                position=np.asarray(origin)+np.asarray(m['size_m'])/2) for m,origin in zip(self.model['magnets'],origins)])
        offset=.0414;shift=translation(self.sim,self.model,offset)
        finite=magnets([m['origin_m'] for m in self.model['magnets']])
        exported=magnets([np.asarray(m['origin_m'])-shift for m in self.model['magnets']])
        points=np.array([[.02,.002,0.],[.04,.006,-.0008],[.06,.001,-.0004]])
        np.testing.assert_allclose(exported.getB(points),finite.getB(points+shift),rtol=1e-11,atol=1e-13)
