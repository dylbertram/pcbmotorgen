import unittest

import numpy as np

from audit_static_material_controls import control_request,compare


class StaticMaterialControlsTest(unittest.TestCase):
    def test_each_control_changes_only_its_declared_parameter_family(self):
        base={'mesh':.002,'fer_mesh':.002,'far':.04,'bonus_order':4,'order':2}
        control_request(base,dict(base,mesh=.0015,fer_mesh=.0015),'mesh')
        control_request(dict(base,near_air_mesh=.0012),dict(base,near_air_mesh=.0009),'mesh')
        control_request(base,dict(base,far=.06),'domain')
        control_request(base,dict(base,bonus_order=6),'quadrature')
        for candidate,kind in [(dict(base,mesh=.0015,far=.06),'mesh'),(dict(base,far=.03),'domain'),(dict(base,bonus_order=2),'quadrature'),(base,'mesh')]:
            with self.assertRaises(ValueError):control_request(base,candidate,kind)

    def test_source_dominance_cannot_hide_a_failed_response(self):
        incident=np.array([[0.,0.,1.]]);first=incident+np.array([[.001,0.,0.]])
        second=incident+np.array([[.0011,0.,0.]])
        result=compare(first,second,incident,.02)
        self.assertLess(result['total_relative_error'],.02)
        self.assertGreater(result['response_relative_error'],.02)
        self.assertFalse(result['passed'])
