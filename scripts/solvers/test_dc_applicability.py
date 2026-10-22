from copy import deepcopy
import unittest
from unittest.mock import patch

from dc_applicability import inspect_request
import test_dc_request_contract as fixtures


class ActualDcApplicabilityTest(unittest.TestCase):
    def inputs(self):
        request,fixture,model,closure=fixtures.LiveDcRequestTest().inputs()
        request=dict(request,schema='finite-dc-live-request-v2');request.pop('source_basis_sha256')
        case=dict(case_id='case',label='Actual case',audit_sha256='audit',fixture=fixture,model=model,
            current_geometry=closure,source_hash='qualified-basis')
        return request,[case]

    def test_only_exact_verified_case_is_qualified_and_no_force_is_returned(self):
        request,cases=self.inputs();result=inspect_request(request,cases)
        self.assertEqual(result['state'],'qualified')
        self.assertEqual(result['qualified_case']['case_id'],'case')
        self.assertEqual(result['source_status'],'qualified-exact-basis')
        self.assertNotIn('pm_array_force_n',result)
        self.assertNotIn('command',result)

    def test_unmatched_actual_geometry_requires_preparation_not_a_fallback(self):
        request,cases=self.inputs();original=deepcopy(request);cases[0]['fixture']['sim']['min_trace_m']=.0003
        result=inspect_request(request,cases)
        self.assertEqual(result['state'],'preparation-required')
        self.assertEqual(result['source_status'],'unqualified');self.assertEqual(result['force_status'],'unqualified')
        self.assertIsNone(result['qualified_case']);self.assertEqual(request,original)

    def test_unacknowledged_or_out_of_scope_requests_are_unsupported(self):
        request,cases=self.inputs()
        for key,value in [('placement_acknowledged',False),('current_a',True),('current_a',.2),('pm_offset_x_m',.1)]:
            result=inspect_request(dict(request,**{key:value}),cases)
            self.assertEqual(result['state'],'unsupported');self.assertIsNone(result['qualified_case'])

    def test_curved_geometry_is_unsupported_and_no_registry_means_unqualified(self):
        request,cases=self.inputs();request['winding']['routing']['curves']=[{}]
        self.assertEqual(inspect_request(request,cases)['state'],'unsupported')
        request,_=self.inputs();self.assertEqual(inspect_request(request,[])['state'],'preparation-required')

    def test_empty_placement_or_return_is_not_a_valid_preparation_declaration(self):
        request,cases=self.inputs()
        for key in ['material_model','return_geometry']:
            result=inspect_request(dict(request,**{key:{}}),cases)
            self.assertEqual(result['state'],'unsupported');self.assertIn('Complete physical',result['reason'])

    def test_proved_nonstar_pad_contact_is_unsupported_not_preparation(self):
        request,cases=self.inputs()
        with patch('dc_applicability.witnesses',return_value=[dict(first=dict(net='A'),second=dict(net='B'))]):
            result=inspect_request(request,cases)
        self.assertEqual(result['state'],'unsupported');self.assertIn('Saved via pads overlap',result['reason'])
        self.assertEqual(result['source_status'],'unqualified');self.assertIsNone(result['qualified_case'])
