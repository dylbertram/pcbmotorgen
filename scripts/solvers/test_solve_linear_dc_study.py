import copy
import json
from pathlib import Path
import unittest

from solve_linear_dc_study import validate_controls


class LinearSourceControlsTest(unittest.TestCase):
    def setUp(self):
        self.matrix=json.loads((Path(__file__).parent/'cases/linear-dc-day-acceptance-matrix-20261022.json').read_text())
        self.study=dict(status='prepared-actual-linear-study-no-source-or-force-acceptance')

    def test_declared_curvature4_and6_are_explicit(self):
        for curvature in [4.,6.]:validate_controls(self.matrix,self.study,.0002,curvature,.5,24000000)

    def test_no_implicit_default_or_undeclared_controls(self):
        for mesh,curvature,port,cap in [(.0002,2.,.5,24000000),(.0003,4.,.5,24000000),(.0002,4.,.3,24000000),(.0002,4.,.5,24000001),(.0002,4.,.5,True)]:
            with self.assertRaises(ValueError):validate_controls(self.matrix,self.study,mesh,curvature,port,cap)
        study=copy.deepcopy(self.study);study['status']='running'
        with self.assertRaises(ValueError):validate_controls(self.matrix,study,.0002,4.,.5,24000000)
