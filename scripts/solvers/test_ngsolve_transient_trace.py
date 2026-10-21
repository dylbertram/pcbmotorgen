import unittest

import numpy as np

from audit_ngsolve_transient_trace import trace_arrays


class FETraceArraysTest(unittest.TestCase):
    def fixture(self):
        previous=np.arange(8).reshape(4,2)*.125;following=previous+.25
        return {'previous':previous,'next':following,'midpoints':(previous+following)/2,'equilibrium':np.zeros(2),'dt':.1,'amplitude':.01,'phase':0}

    def test_absolute_continuous_trace_and_headers_are_required(self):
        raw=self.fixture();trace_arrays(raw,2,2,.1,.01,0)
        with self.assertRaisesRegex(ValueError,'header differs'):trace_arrays(raw,2,2,.2,.01,0)
        raw['previous']=raw['previous'].copy();raw['previous'][1,0]+=.001
        with self.assertRaisesRegex(ValueError,'Discontinuous'):trace_arrays(raw,2,2,.1,.01,0)

    def test_midpoint_identity_cannot_be_replaced_by_small_signal_trace(self):
        raw=self.fixture();raw['midpoints']+=.001
        with self.assertRaisesRegex(ValueError,'midpoint identity'):trace_arrays(raw,2,2,.1,.01,0)
