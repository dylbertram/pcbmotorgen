from copy import deepcopy
import unittest

from finite_current_pose_inputs import pose_forces
from finite_current_zero_bias import posed_model


class PoseReferenceInputTest(unittest.TestCase):
    def inputs(self):
        model = {'magnets': [{'origin_m': [0., 0., .001]}], 'stack': []}
        posed = posed_model(model, .0001)
        cache = dict(model=model, source_work='/actual/source')
        level = dict(pm_force_n=[.1, 0., 0.], copper_force_n=[-.1, 0., 0.],
                     power_relative_error=0., volume_relative_error=0., current_relative_error=0.,
                     mesh_cad_relative_difference=.003, action_reaction_error_n=0.)
        reference = dict(status='passed-affine-rt0-bare-pose-forces-only', failures=[], model=model,
            original_reference_control={'passed': True},
            source_work='/actual/source', effective_loop_current_a=.2,
            input_hashes={'/actual/source/summary.json': 'source-hash'},
            poses={'0.0001': dict(magnets=posed['magnets'], levels={'2': level, '4': deepcopy(level)},
                                  pm_force_n_per_loop_a=[.5, 0., 0.], copper_force_n_per_loop_a=[-.5, 0., 0.])})
        return cache, {'model': posed}, reference

    def test_exact_pose_and_source_are_required_not_nominal_replay(self):
        cache, bias, reference = self.inputs()
        model, pm, _ = pose_forces(cache, bias, reference, .0001, 'source-hash', .2)
        self.assertEqual(model, bias['model'])
        self.assertEqual(pm.tolist(), [.5, 0., 0.])
        for offset, digest in [(0., 'source-hash'), (.0001, 'changed-source')]:
            with self.assertRaises(ValueError):
                pose_forces(cache, bias, reference, offset, digest, .2)

    def test_partial_failed_nonfinite_or_wrong_units_cannot_enter_coupling(self):
        for mutation in ['partial', 'failed', 'nonfinite', 'units']:
            cache, bias, reference = self.inputs()
            if mutation == 'partial':reference['status'] = 'completed-bare-pose-runtime-preflight-only'
            if mutation == 'failed':reference['failures'] = ['quadrature']
            if mutation == 'nonfinite':reference['poses']['0.0001']['levels']['4']['power_relative_error'] = float('nan')
            if mutation == 'units':reference['poses']['0.0001']['pm_force_n_per_loop_a'][0] = .1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                pose_forces(cache, bias, reference, .0001, 'source-hash', .2)
