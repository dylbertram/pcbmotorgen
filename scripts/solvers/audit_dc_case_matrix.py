#!/usr/bin/env python3
"""Audit the recorded actual-geometry DC matrix, never serve cached app results.

Certifies only the enumerated physical case/current basis and sampled poses and
currents. General geometry, interpolation, componentwise relative error bounds,
hardware/material/thermal/reversal/inductance and live app recalculation remain
outside this evidence. Force gates use vector norms and an absolute 1e-8 N floor;
current-induced force is checked separately from total PM bias.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_finite_current_controls import compare
from finite_current_coupling import control_model
from finite_current_zero_bias import posed_model
from source_snapshot import capture

CURRENTS = {'0.0', '0.1', '-0.1', '0.5', '-0.5'}
ACCEPTED = 'passed-recorded-finite-current-static-pilot-only'


def validate_state_report(report, model, mode, pose, formulation, order, degree):
    if report.get('status') != ACCEPTED or report.get('failures') != []:
        raise ValueError('Partial or failed coupled state cannot enter a case audit')
    if report.get('model') != control_model(posed_model(model, pose), mode):
        raise ValueError('State uses different material geometry, law or PM pose')
    if (report.get('formulation') != formulation or report.get('field_order') != order or
        report.get('degree') != degree or set(report.get('states', {})) != CURRENTS):
        raise ValueError('Missing current states or incorrect declared discretization')
    for state in report['states'].values():
        pm = np.asarray(state['pm_array_force_n'])
        stationary = np.asarray(state['combined_stationary_force_n'])
        residual = state['relative_residual']
        if (pm.shape != (3,) or stationary.shape != (3,) or not np.isfinite([pm, stationary]).all() or
            not np.isfinite(residual) or not 0 <= residual <= 1e-9):
            raise ValueError('Nonfinite force or unconverged equilibrium in matrix')
        if np.linalg.norm(pm+stationary) > max(1e-8, .02*float(np.linalg.norm(pm))):
            raise ValueError('State action/reaction balance fails unchanged gate')
    if any(not value.get('passed') for value in report.get('incremental_balance', {}).values()) or set(report.get('incremental_balance', {})) != CURRENTS-{'0.0'}:
        raise ValueError('Missing or failed current-induced force-balance controls')
    if mode in ['linear', 'vacuum']:
        parity = report.get('linear_current_parity', {})
        if set(parity) != {'0.1', '0.5'} or any(not value.get('passed') for value in parity.values()):
            raise ValueError('Missing or failed linear/vacuum polarity limits')


def matrix_plan():
    jobs, pairs = {}, []
    def job(key, stem, mode, pose, formulation, order, degree=8):
        jobs[key] = dict(work=stem+'-20261021', mode=mode, pose=pose, formulation=formulation, order=order, degree=degree)
    for name, pose in [('nominal', 0.), ('plus100um', .0001), ('minus100um', -.0001)]:
        for formulation, short in [('vector-b', 'vector'), ('scalar-h', 'scalar')]:
            for level in ['coarse', 'refined', 'domain', 'quadrature']:
                if name == 'nominal':
                    suffix = {'coarse': ('-v2' if short == 'vector' else '-v1'),
                              'refined': '-refined-v1', 'domain': '-domain06-v1', 'quadrature': '-degree6-v1'}[level]
                else:
                    suffix = {'coarse': '-'+name+'-v1', 'refined': '-refined-'+name+'-v1',
                              'domain': '-domain06-'+name+'-v1', 'quadrature': '-degree6-'+name+'-v1'}[level]
                job(name+'/'+short+'/'+level, 'dc-finite-current-nonlinear-'+short+suffix,
                    'nonlinear', pose, formulation, 1 if short == 'vector' else 2, 6 if level == 'quadrature' else 8)
            for level in ['refined', 'domain', 'quadrature']:
                pairs.append((name+'/'+short+'/'+level, name+'/'+short+'/coarse', 'refinement'))
        for level in ['coarse', 'refined', 'domain', 'quadrature']:
            pairs.append((name+'/vector/'+level, name+'/scalar/'+level, 'formulation'))
        key = name+'/vector/opening'
        job(key, 'dc-finite-current-nonlinear-vector-opening0075-'+name+'-v1', 'nonlinear', pose, 'vector-b', 1)
        pairs.append((key, name+'/vector/coarse', 'refinement'))
    for short, formulation, order in [('vector', 'vector-b', 2), ('scalar', 'scalar-h', 3)]:
        for level, suffix in [('coarse', '-v1'), ('refined', '-refined-v1'), ('domain', '-domain06-v1'), ('quadrature', '-degree6-v1')]:
            job('linear/'+short+'/'+level, 'dc-finite-current-linear-'+short+'-order'+str(order)+suffix,
                'linear', 0., formulation, order, 6 if level == 'quadrature' else 8)
        for level in ['refined', 'domain', 'quadrature']:
            pairs.append(('linear/'+short+'/'+level, 'linear/'+short+'/coarse', 'refinement'))
    for level in ['coarse', 'refined', 'domain', 'quadrature']:
        pairs.append(('linear/vector/'+level, 'linear/scalar/'+level, 'formulation'))
    job('linear/vector/opening', 'dc-finite-current-linear-vector-opening0075-nominal-v1', 'linear', 0., 'vector-b', 2)
    pairs.append(('linear/vector/opening', 'linear/vector/coarse', 'refinement'))
    job('vacuum', 'dc-finite-current-vacuum-vector-v2', 'vacuum', 0., 'vector-b', 1)
    return jobs, pairs


def comparison_order(first, second, kind, quadrature_finer=False):
    # Recorded quadrature variants are degree6 versus the baseline degree8. Other
    # variants, and a declared finer quadrature rule, are the reference.
    coarser_variant = first.endswith('/quadrature') and not quadrature_finer
    return (second, first) if kind == 'refinement' and not coarser_variant else (first, second)


class Evidence:
    def __init__(self):
        self.hashes, self.identities = {}, {}

    @staticmethod
    def identity(path):
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def digest(self, path):
        path = Path(path).resolve()
        if path not in self.hashes:
            before = self.identity(path)
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(block)
            if before != self.identity(path):
                raise ValueError('Evidence changed while hashing')
            self.hashes[path], self.identities[path] = digest.hexdigest(), before
        return self.hashes[path]

    def report(self, path, option='--work'):
        path = Path(path).resolve()
        self.digest(path)
        report = json.loads(path.read_text())
        receipt_path = Path(report['command_receipt'])
        self.digest(receipt_path)
        receipt = json.loads(receipt_path.read_text())
        command = receipt['command']
        expected = str(path.parent) if option == '--work' else str(path)
        if (receipt.get('status') != 'completed' or type(receipt.get('exit_code')) is not int or
            receipt['exit_code'] != 0 or option not in command or command[command.index(option)+1] != expected):
            raise ValueError('Missing successful receipt bound to this exact evidence job')
        for name, expected_hash in report.get('input_hashes', {}).items():
            if self.digest(name) != expected_hash:
                raise ValueError('Immutable physical input hash changed')
        for entry in report['source_snapshots'].values():
            if self.digest(path.parent/entry['snapshot']) != entry['sha256']:
                raise ValueError('Archived implementation snapshot changed')
        return report

    def unchanged(self):
        if any(self.identity(path) != identity for path, identity in self.identities.items()):
            raise ValueError('Evidence changed during the matrix audit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--case-plan', type=Path, help='declared non-recorded case: job works, material/source/section reports')
    parser.add_argument('--matrix-component-only', action='store_true', help='Inspect a declared magnetic matrix before source-force controls finish; output cannot admit or register a case')
    args = parser.parse_args()
    if args.matrix_component_only and not args.case_plan:
        parser.error('Component-only inspection requires a new declared case; do not repeat the accepted recorded matrix')
    root, work = args.archive_root.resolve(), args.work.resolve()
    if work.exists():
        parser.error('Preserve previous case audits')
    started = time.monotonic()
    implementation_files = [Path(__file__), *[Path(__file__).with_name(name) for name in
        ['compare_finite_current_controls.py', 'finite_current_coupling.py', 'finite_current_zero_bias.py']]]
    implementation_hashes = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in implementation_files}
    evidence = Evidence()
    case = json.loads(args.case_plan.read_text()) if args.case_plan else None
    if case:
        implementation_files.append(args.case_plan.resolve())
        implementation_hashes[str(args.case_plan.resolve())] = hashlib.sha256(args.case_plan.read_bytes()).hexdigest()
    material_path = Path(case['material_work'])/'summary.json' if case else root/'dc03-approved-35um-clearance-v1-20261021/summary.json'
    source_path = Path(case['source_work'])/'summary.json' if case else root/'dc-source-curvature4-rt0-export-v1-20261021/summary.json'
    material = evidence.report(material_path)
    source = evidence.report(source_path)
    if (material['status'] != 'completed-approved-disjoint-material-geometry-only' or material['failures'] or
        source['status'] != 'passed-affine-rt0-source-export-only' or material['current_source_work'] != source['source_work']):
        raise ValueError('Approved actual geometry and accepted finite-current source required')
    source_summary = source_path
    source_hash = evidence.digest(source_summary)
    sections = evidence.report(Path(case['sections_report']) if case else root/'dc-source-curvature4-all-eligible-sections-20261021.json', '--output')
    expected_sections = case['expected_sections'] if case else 501
    current_work = Path(source['source_work'])
    if (sections['status'] != 'passed-finite-dc-all-eligible-winding-sections-only' or sections['failures'] or
        sections['selection'] != 'all eligible' or sections['expected_sections'] != expected_sections or len(sections['sections']) != expected_sections or
        sections['source_work'] != str(current_work) or
        sections['source_summary_sha256'] != evidence.digest(current_work/'summary.json') or
        sections['source_solution_sha256'] != evidence.digest(current_work/'dc-current-potential.sol')):
        raise ValueError('Whole actual-source eligible-section qualification is missing or mismatched')
    for section in sections['sections']:
        numbers = [section['relative_area_error'], section['absolute_current_difference_per_loop_a'], section['reference_per_loop_a']]
        if (not section['passed'] or not np.isfinite(numbers).all() or not 0 <= numbers[0] <= .02 or
            not 0 <= numbers[1] <= max(1e-8, .05*abs(numbers[2]))):
            raise ValueError('Signed current section fails unchanged source controls')
    source_control_path=None
    if case and not args.matrix_component_only:
        from audit_linear_dc_source_force_controls import verify_source_force_audit
        if not case.get('source_control_audit'):
            raise ValueError('New case admission requires its complete source-refinement force audit')
        source_control_path=(root/case['source_control_audit']).resolve()
        verify_source_force_audit(evidence,source_control_path,material['model'],evidence.digest(current_work/'summary.json'))
        implementation=Path(__file__).with_name('audit_linear_dc_source_force_controls.py')
        implementation_files.append(implementation)
        implementation_hashes[str(implementation.resolve())]=hashlib.sha256(implementation.read_bytes()).hexdigest()
    jobs, pairs = matrix_plan()
    if case:
        if set(case['jobs']) != set(jobs):
            raise ValueError('Declared case plan must cover exactly the recorded coverage template')
        jobs = case['jobs']
    reports, controls = {}, {}
    for key, request in jobs.items():
        path = (Path(request['work']) if Path(request['work']).is_absolute() else root/request['work'])/'summary.json'
        report = evidence.report(path)
        validate_state_report(report, material['model'], request['mode'], request['pose'],
                              request['formulation'], request['order'], request['degree'])
        if report.get('version') != source['version']:
            raise ValueError('Matrix engine differs from the pinned finite-current source')
        if report['input_hashes'].get(str(source_summary)) != source_hash:
            raise ValueError('Matrix changed the actual prescribed current source')
        for state in report['states'].values():
            if evidence.digest(path.parent/state['solution']) != state['solution_sha256']:
                raise ValueError('Saved magnetic solution changed')
        reports[key] = report
    for first, second, kind in pairs:
        left, right = comparison_order(first, second, kind, bool(case and case.get('quadrature_finer')))
        values = compare(reports[left], reports[right], kind)
        if not all(value['passed'] for value in values.values()):
            raise ValueError('Matrix control fails unchanged gate: '+first+' versus '+second)
        controls[first+'--'+second] = dict(kind=kind, first=left, reference=right, values=values)
    evidence.unchanged()
    work.mkdir(parents=True)
    snapshots = capture(work, implementation_files)
    if any(snapshots[path]['sha256'] != digest for path, digest in implementation_hashes.items()):
        raise ValueError('Case-audit implementation changed during verification')
    result = dict(status=('passed-declared-magnetic-matrix-component-not-admission' if args.matrix_component_only else
                         'passed-declared-case-actual-geometry-dc-force-matrix-only' if case else 'passed-recorded-actual-geometry-dc-force-matrix-only'), scope=__doc__,
                  current_points_a=sorted(float(value) for value in CURRENTS), pose_offsets_x_m=[0., .0001, -.0001],
                  magnetic_jobs=len(jobs), saved_current_states=len(jobs)*len(CURRENTS), control_pairs=len(pairs),
                  actual_model=material['model'], prescribed_source_summary_sha256=source_hash,
                  current_section_eligibility=sections['eligibility'], qualified_eligible_sections=expected_sections,
                   case_plan=str(args.case_plan.resolve()) if case else None,
                   source_refinement_force_audit=str(source_control_path) if source_control_path else None,
                   component_only=args.matrix_component_only,
                  force_floor_n=1e-8, refinement_gate=.02, formulation_gate=.05,
                  evidence_hashes={str(path): digest for path, digest in evidence.hashes.items()}, controls=controls,
                  source_snapshots=snapshots,
                  seconds=time.monotonic()-started, app_integration='not-performed; archived forces must not replace live geometry recalculation')
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        result['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    (work/'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
