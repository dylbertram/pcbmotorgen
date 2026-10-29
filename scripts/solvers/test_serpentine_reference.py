import copy
import json
import unittest

import numpy as np

from serpentine_reference import GEOMETRY, PHYSICAL, calculate


class SerpentineReferenceTest(unittest.TestCase):
    def test_goals_and_obsolete_fixture_force_values_are_not_reference_inputs(self):
        old=json.loads(GEOMETRY.read_text())
        coils=old['coils_serpentine']
        baseline=calculate(coils,PHYSICAL,20)
        changed=dict(PHYSICAL,target_force_n=100.,peak_force_n=.001,max_accel_m_s2=0.,voltage_headroom=.001)
        old['force_sweep']={'mean_thrust_mn':1e99,'ripple_pct':0.}
        self.assertEqual(calculate(coils,changed,20),baseline)

    def test_actual_excitation_and_material_changes_do_change_the_reference(self):
        coils=json.loads(GEOMETRY.read_text())['coils_serpentine']
        base=np.asarray(calculate(coils,PHYSICAL,20)['force_xyz_n'])
        doubled=dict(PHYSICAL,max_current_a=2.)
        np.testing.assert_allclose(calculate(coils,doubled,20)['force_xyz_n'],2*base,rtol=1e-12,atol=1e-14)
        reversed_polarity=dict(PHYSICAL,magnet_remanence_t=-PHYSICAL['magnet_remanence_t'])
        np.testing.assert_allclose(calculate(coils,reversed_polarity,20)['force_xyz_n'],-base,rtol=1e-12,atol=1e-14)

    def test_segment_direction_is_physical_in_this_explicit_current_fixture(self):
        coils=json.loads(GEOMETRY.read_text())['coils_serpentine']
        reversed_coils=copy.deepcopy(coils)
        for coil in reversed_coils:
            for segment in coil['segments']:
                segment['start_mm'],segment['end_mm']=segment['end_mm'],segment['start_mm']
        base=np.asarray(calculate(coils,PHYSICAL,20)['force_xyz_n'])
        np.testing.assert_allclose(calculate(reversed_coils,PHYSICAL,20)['force_xyz_n'],-base,rtol=1e-12,atol=1e-14)
