#!/usr/bin/env python3
"""Fresh recorded-geometry DC magnetic job from a complete actual request.

No archived forces are returned. Eligibility compares every actual routed graph,
copper depth/dimension/resistivity, declared finite return and explicit material
placement to the audited source case. That exact-keyed immutable finite-current
basis/material rule may be reused, but the nonlinear field is solved anew.
This is the offline live-request boundary, not a general app solver release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from audit_dc_case_matrix import Evidence
from check_free_space import run
from dc_request_contract import validate_request
from source_snapshot import capture

QUALIFIED_AUDIT_SHA256 = '6cfab100944bc80d3312da9bd6b3f5e66b2afa3c623f56e8d643b214a1dedb9f'


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
    audit_path = root/'dc-recorded-case-force-matrix-audit-v2-20261021/summary.json'
    if evidence.digest(audit_path) != QUALIFIED_AUDIT_SHA256:
        raise ValueError('Only the explicitly registered recorded-case qualification is admitted')
    audit = evidence.report(audit_path)
    if (audit.get('status') != 'passed-recorded-actual-geometry-dc-force-matrix-only' or
        audit.get('magnetic_jobs') != 37 or audit.get('saved_current_states') != 185 or audit.get('control_pairs') != 44):
        raise ValueError('Complete recorded-case verification matrix required')
    for path, digest in audit['evidence_hashes'].items():
        if evidence.digest(path) != digest:
            raise ValueError('Recorded numerical qualification evidence changed')
    fixture_paths = [Path(path) for path in audit['evidence_hashes'] if path.endswith('/mesh-80/fixture.json')]
    if len(fixture_paths) != 1:
        raise ValueError('Ambiguous qualified physical winding geometry')
    fixture = json.loads(fixture_paths[0].read_text())
    source_path = root/'dc-source-curvature4-rt0-export-v1-20261021/summary.json'
    source = evidence.report(source_path)
    current = evidence.report(Path(source['source_work'])/'summary.json')
    request_hash = evidence.digest(request_path)
    request_bytes = unchanged_request_bytes(request_path, request_hash)
    request = json.loads(request_bytes)
    eligibility = validate_request(request, fixture, audit['actual_model'], current['geometry'], evidence.digest(source_path))
    evidence.unchanged()
    # Input is copied only after eligibility. Preserve caller bytes; no repairing
    # geometry, shifting materials, filling return paths or rounded current.
    work.mkdir(parents=True)
    request_copy = work/'request.json'
    request_copy.write_bytes(request_bytes)
    snapshots = capture(work, [Path(__file__), Path(__file__).with_name('dc_request_contract.py')])
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
        offset = request['pm_offset_x_m']
        pose = {0.: 'nominal', .0001: 'plus100um', -.0001: 'minus100um'}[offset]
        bias = 'dc-zero-current-bias-v1-20261021' if not offset else 'dc-zero-current-vector-'+pose+'-v3-20261021'
        command = [sys.executable, str(Path(__file__).with_name('finite_current_coupling.py').resolve()),
            '--cache-work', str(root/'dc-source-material-cache-opening0075-v1-20261021'),
            '--bias-work', str(root/bias), '--bare-force', str(root/'finite-copper-dc-curvature4-amg-bare-pm-force-20261020.json'),
            '--pose-reference-work', str(root/'dc-affine-bare-pose-forces-v2-20261021'),
            '--pm-offset-x', str(float(offset)), '--mode', 'nonlinear', '--threads', '2', '--work', str(work/'fresh-magnetic-solve')]
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
        report.update(status='passed-fresh-recorded-geometry-dc-request-only',
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
