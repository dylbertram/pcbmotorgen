import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from audit_motion_trace import relative_difference,selected_result
from periodic_motion import run,save_trace


class MotionTraceTest(unittest.TestCase):
    def test_an_incomplete_study_cannot_be_rescued_by_selecting_one_trace(self):
        record={'status':'failed','runs':{'gap':{'trace':'not enough'}}}
        with self.assertRaises(ValueError):selected_result(record,'gap')
        record['status']='passed-periodic-nonlinear-motion-numerics-only'
        self.assertEqual(selected_result(record,'gap'),record['runs']['gap'])
        with self.assertRaises(ValueError):selected_result(record,'missing')

    def test_traces_are_hashed_and_existing_data_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'zero.npz'
            result=run(0,cells=4,modes=1,samples=32,wall_cells=8,trace_path=path)
            self.assertEqual(result['trace']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            before=path.read_bytes()
            with self.assertRaises(FileExistsError):save_trace(path,changed=np.zeros(1))
            self.assertEqual(path.read_bytes(),before)
            with np.load(path,allow_pickle=False) as archive:self.assertGreater(archive['equilibrium'].size,0)
            self.assertEqual(result['sampled_material_state']['quadrature_fraction_crossing_knee'],0)

    def test_trace_shape_or_nonfinite_integrals_cannot_hide_a_difference(self):
        self.assertEqual(relative_difference([1,2],[1,2]),0)
        self.assertGreater(relative_difference([1,3],[1,2]),0.1)
        with self.assertRaises(ValueError):relative_difference([1],[1,2])
        with self.assertRaises(ValueError):relative_difference([float('nan')],[1])


if __name__=='__main__':unittest.main()
