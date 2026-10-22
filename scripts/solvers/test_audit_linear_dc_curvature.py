from copy import deepcopy
import unittest

from audit_linear_dc_curvature import isolated_curvature


class IsolatedCurvatureTest(unittest.TestCase):
    def reports(self):
        first=dict(version='pinned',input_hashes={'physical':'same'},geometry={'return':'actual'},
            request=dict(mesh_m=.0002,curvature_safety=6,port_fraction=.5),mesh_elements=100)
        second=deepcopy(first);second['request']['curvature_safety']=8;second['mesh_elements']=200
        return first,second

    def test_only_a_finer_curvature_on_identical_physical_inputs_is_permitted(self):
        first,second=self.reports();isolated_curvature(first,second)
        for kind in ['mesh','port','physical','not-finer']:
            a,b=self.reports()
            if kind=='mesh':b['request']['mesh_m']=.00015
            elif kind=='port':b['request']['port_fraction']=.4
            elif kind=='physical':b['geometry']['return']='other'
            else:b['mesh_elements']=100
            with self.assertRaises(ValueError):isolated_curvature(a,b)
