from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from dc_request_contract import UnsupportedDcRequest, validate_request
from recalculate_dc_request import select_case
from dc_qualified_cases import AUDIT_STATUSES,verify_case
from test_dc_request_contract import LiveDcRequestTest


def case_from(fixture, model, closure, case_id='case', source='qualified-basis'):
    return dict(case_id=case_id, label=case_id, audit_sha256='audit-'+case_id, fixture=fixture, model=model,
                current_geometry=closure, source_hash=source, live={})


class QualifiedCaseSelectionTest(unittest.TestCase):
    def test_matrix_component_status_is_never_an_admission_status(self):
        self.assertNotIn('passed-declared-magnetic-matrix-component-not-admission',AUDIT_STATUSES)

    def test_new_case_cannot_register_with_only_the_37_job_force_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();audit=root/'audit.json';fixture=root/'fixture.json';source=root/'source/summary.json'
            cache=root/'cache/summary.json';bias=root/'bias/summary.json';bare=root/'bare.json'
            hashes={str(p):'hash-'+p.name for p in [fixture,source,cache,bias,bare]}
            report=dict(status='passed-declared-case-actual-geometry-dc-force-matrix-only',magnetic_jobs=37,
                saved_current_states=185,control_pairs=44,evidence_hashes=hashes,actual_model={})
            reports={str(audit):report,str(source):dict(source_work=str(root/'current')),str(root/'current/summary.json'):dict(geometry={})}
            evidence=SimpleNamespace(digest=lambda p:'audit-hash' if Path(p)==audit else hashes[str(p)],report=lambda p:reports[str(p)])
            entry=dict(case_id='unqualified-source-controls',label='actual',audit=str(audit),audit_sha256='audit-hash',
                fixture=str(fixture),source=str(root/'source'),live={pose:dict(cache=str(root/'cache'),bias=str(root/'bias'),bare=str(bare))
                    for pose in ['nominal','plus100um','minus100um']})
            with self.assertRaisesRegex(ValueError,'downstream source-refinement'):verify_case(root,entry,evidence)

    def v2(self):
        request, fixture, model, closure = LiveDcRequestTest().inputs()
        request = dict(request, schema='finite-dc-live-request-v2');del request['source_basis_sha256']
        return request, fixture, model, closure

    def test_v2_request_selects_exactly_one_matching_registered_case(self):
        request, fixture, model, closure = self.v2()
        other = deepcopy(fixture);other['sim']['min_trace_m'] = .0003
        case, eligibility = select_case(request, [case_from(other, model, closure, 'other'), case_from(fixture, model, closure)])
        self.assertEqual(case['case_id'], 'case')
        self.assertEqual(eligibility['status'], 'eligible-for-qualified-geometry-live-recalculation-only')
        self.assertNotIn('pm_array_force_n', eligibility)

    def test_unmatched_or_ambiguous_designs_need_qualification(self):
        request, fixture, model, closure = self.v2()
        changed = deepcopy(request);changed['winding']['sim']['min_trace_m'] = .00021
        with self.assertRaisesRegex(UnsupportedDcRequest, 'Qualification required'):
            select_case(changed, [case_from(fixture, model, closure)])
        with self.assertRaisesRegex(UnsupportedDcRequest, 'ambiguous'):
            select_case(request, [case_from(fixture, model, closure, 'a'), case_from(fixture, model, closure, 'b')])
        with self.assertRaisesRegex(UnsupportedDcRequest, 'Qualification required'):
            select_case(request, [])

    def test_v2_cannot_smuggle_a_basis_and_v1_keeps_its_explicit_basis(self):
        request, fixture, model, closure = self.v2()
        with self.assertRaisesRegex(UnsupportedDcRequest, 'versioned'):
            validate_request(dict(request, source_basis_sha256='qualified-basis'), fixture, model, closure, 'qualified-basis')
        original, *_ = LiveDcRequestTest().inputs()
        with self.assertRaisesRegex(UnsupportedDcRequest, 'different or unqualified'):
            validate_request(original, fixture, model, closure, 'another-basis')
