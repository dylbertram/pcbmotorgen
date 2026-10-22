#!/usr/bin/env python3
"""Fresh qualified-geometry DC magnetic job from a complete actual request.

No archived forces are returned. Eligibility compares every actual routed graph,
copper depth/dimension/resistivity, declared finite return and explicit material
placement to each registered, re-verified qualified case; exactly one must match.
That case's exact-keyed immutable finite-current basis/material rule may be
reused, but the nonlinear field is solved anew. Unmatched designs need their own
offline qualification. This is the live-request boundary, not a general solver.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from audit_dc_case_matrix import Evidence
from check_free_space import run
from dc_qualified_cases import read_registry, verify_case
from dc_request_contract import UnsupportedDcRequest, validate_request
from source_snapshot import capture

QUALIFIED_AUDIT_SHA256 = '6cfab100944bc80d3312da9bd6b3f5e66b2afa3c623f56e8d643b214a1dedb9f'


def select_case(request, cases):
    """Exactly one independently verified case must match; no nearest match."""
    matches, reasons = [], []
    for case in cases:
        try:
            matches.append((case, validate_request(request, case['fixture'], case['model'], case['current_geometry'], case['source_hash'])))
        except UnsupportedDcRequest as error:
            reasons.append(case['case_id']+': '+str(error))
    if len(matches) != 1:
        detail = '; '.join(reasons) if not matches else 'ambiguous registered cases'
        raise UnsupportedDcRequest('Qualification required: this design matches no single registered qualified linear DC case ('+detail+')')
    return matches[0]


def unchanged_request_bytes(path, expected_hash):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('Request content changed; result is stale and must not be returned')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    request_path, root, work = [path.resolve() for path in [args.request, args.archive_root, args.work]]
    if work.exists():
        parser.error('Fresh result directory required; never overwrite earlier requests')
    evidence = Evidence()
    request_hash = evidence.digest(request_path)
    request_bytes = unchanged_request_bytes(request_path, request_hash)
    request = json.loads(request_bytes)
    entries = read_registry(root)['cases']
    if request.get('schema') == 'finite-dc-live-request-v1':
        # The original recorded-basis request remains bound to that one audit.
        entries = [entry for entry in entries if entry['audit_sha256'] == QUALIFIED_AUDIT_SHA256]
    cases = [verify_case(root, entry, evidence) for entry in entries]
    case, eligibility = select_case(request, cases)
    eligibility['qualified_case'] = dict(case_id=case['case_id'], label=case['label'], audit_sha256=case['audit_sha256'])
    evidence.unchanged()
    # Input is copied only after eligibility. Preserve caller bytes; no repairing
    # geometry, shifting materials, filling return paths or rounded current.
    work.mkdir(parents=True)
    request_copy = work/'request.json'
    request_copy.write_bytes(request_bytes)
    snapshots = capture(work, [Path(__file__), *[Path(__file__).with_name(n) for n in ['dc_request_contract.py', 'dc_qualified_cases.py']]])
    report = dict(status='validated-live-request-no-force-result', scope=__doc__, eligibility=eligibility,
                  source_snapshots=snapshots, evidence_hashes={str(path): digest for path, digest in evidence.hashes.items()},
                  input_request=str(request_path), input_request_sha256=request_hash)
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    if args.validate_only:
        return
    try:
        offset = float(request['pm_offset_x_m'])
        live = case['live'][offset]
        command = [sys.executable, str(Path(__file__).with_name('finite_current_coupling.py').resolve()),
            '--cache-work', live['cache'], '--bias-work', live['bias'], '--bare-force', live['bare']]
        if live.get('pose_reference'):
            command += ['--pose-reference-work', live['pose_reference']]
        command += ['--pm-offset-x', str(offset), '--mode', 'nonlinear', '--threads', '2', '--work', str(work/'fresh-magnetic-solve')]
        report['status'] = 'running-live-request';save()
        # Inherit the outer live-job group: killing/cancelling that owned group
        # must stop both this worker and its numerical child, not orphan it in
        # a nested detached session. The magnetic child launches no processes.
        run(command, work, 'fresh-magnetic-solve.log', new_process_group=False)
        solved = evidence.report(work/'fresh-magnetic-solve/summary.json')
        if solved['status'] != 'passed-recorded-finite-current-static-pilot-only' or solved['failures']:
            raise ValueError('Fresh request field/force controls failed')
        # Select only a freshly solved state, never an archived force lookup.
        state = solved['states'][str(float(request['current_a']))]
        evidence.unchanged()
        unchanged_request_bytes(request_path, request_hash)
        if evidence.digest(request_copy) != evidence.digest(request_path):
            raise ValueError('Request changed while the field was solving; result is stale')
        for path, entry in snapshots.items():
            if evidence.digest(path) != entry['sha256']:
                raise ValueError('Live request implementation changed during solve')
        report.update(status='passed-fresh-qualified-geometry-dc-request-only', qualified_case=eligibility['qualified_case'],
                      fresh_solution=str(Path('fresh-magnetic-solve')/state['solution']),
                      fresh_solution_sha256=state['solution_sha256'], pm_array_force_n=state['pm_array_force_n'],
                      fresh_solve_summary_sha256=evidence.digest(work/'fresh-magnetic-solve/summary.json'),
                      reused_source_scope='Exact-keyed immutable prescribed-current basis and material integration rule only; field and force freshly recomputed.',
                      evidence_hashes={str(path): digest for path, digest in evidence.hashes.items()})
        save()
    except BaseException as error:
        report.update(status='failed-live-dc-request-no-force-result', error=str(error))
        for key in ['pm_array_force_n', 'fresh_solution', 'fresh_solution_sha256']:
            report.pop(key, None)
        save();raise


if __name__ == '__main__':
    main()
