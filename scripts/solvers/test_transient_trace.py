import tempfile
import unittest
from pathlib import Path

import numpy as np

from audit_transient_trace import audit_states
from spectral_transient import run


class MidpointTraceTest(unittest.TestCase):
    def test_recomputes_physics_and_rejects_changed_states_or_power(self):
        request={'thickness':.0002,'mu':130.,'bsat':1000.,'frequency':1000.,'fraction':.001,'phase':0,
            'cells':4,'modes':1,'samples':32,'wall_cells':8,'gap_cells':2,'steps_per_period':32,
            'periods':4,'layer_conductivity':.2,'harmonic_initial_guess':True}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.npz';result=run(**request,trace_path=path)
            with np.load(path) as source:raw={name:source[name].copy() for name in source.files}
            proof=audit_states(request,result,raw)
            self.assertEqual(proof['checked_steps'],64)
            self.assertLess(proof['maximum_recomputed_relative_equation_residual'],1e-10)
            for name in ['midpoints','loss','amplitude']:
                changed={key:value.copy() for key,value in raw.items()}
                changed[name].flat[0]+=1e-5
                with self.assertRaises(ValueError):audit_states(request,result,changed)
