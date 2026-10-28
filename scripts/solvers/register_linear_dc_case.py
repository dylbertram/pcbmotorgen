#!/usr/bin/env python3
"""Register one case whose whole force-matrix audit passed, for live recalculation.

Live inputs are taken from the audited finest-opening nonlinear vector job's
own successful receipt at each PM pose; nothing is typed in by hand. The entry
is verified exactly as the live worker verifies it before it is appended.
Existing entries are never rewritten. No force is stored.
"""
import argparse
import json
import os
from pathlib import Path

from audit_dc_case_matrix import Evidence
from dc_qualified_cases import REGISTRY, declaration, read_registry, verify_case
from post_project_force import sha

RECORDED = dict(audit='dc-recorded-case-force-matrix-audit-v2-20261021/summary.json',
    source='dc-source-curvature4-rt0-export-v1-20261021',
    fixture='winding-star2-v1-copper-20261020/free-space-copper-audit/mesh-80/fixture.json',
    live={pose: dict(cache='dc-source-material-cache-opening0075-v1-20261021',
                     bias='dc-zero-current-bias-v1-20261021' if pose == 'nominal' else 'dc-zero-current-vector-'+pose+'-v3-20261021',
                     bare='finite-copper-dc-curvature4-amg-bare-pm-force-20261020.json', pose_reference='dc-affine-bare-pose-forces-v2-20261021')
          for pose in ['nominal', 'plus100um', 'minus100um']})


def option(command, name):
    return command[command.index(name)+1] if name in command else None


def from_case_plan(root, plan_path, audit):
    plan = json.loads(Path(plan_path).read_text())
    if audit.get('case_plan') != str(Path(plan_path).resolve()):
        raise ValueError('Audit was not produced from this case plan')
    live = {}
    for pose in ['nominal', 'plus100um', 'minus100um']:
        work = Path(root)/plan['jobs'][pose+'/vector/opening']['work']
        receipt = json.loads((work.parent/(work.name+'.log.command.json')).read_text())
        if receipt.get('status') != 'completed' or receipt.get('exit_code') != 0:
            raise ValueError('Audited live template job has no successful receipt')
        command = receipt['command']
        live[pose] = dict(cache=option(command, '--cache-work'), bias=option(command, '--bias-work'),
                          bare=option(command, '--bare-force'), pose_reference=option(command, '--pose-reference-work'))
    material = json.loads((Path(plan['material_work'])/'summary.json').read_text())
    fixtures = [p for p in material['input_hashes'] if p.endswith('/fixture.json')]
    if len(fixtures) != 1:
        raise ValueError('Ambiguous audited fixture')
    return dict(source=plan['source_work'], fixture=fixtures[0], live=live)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--label', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--recorded', action='store_true')
    group.add_argument('--case-audit', type=Path)
    parser.add_argument('--case-plan', type=Path)
    args = parser.parse_args()
    root = args.archive_root.resolve()
    registry = read_registry(root)
    if any(entry['case_id'] == args.case_id for entry in registry['cases']):
        parser.error('Case already registered; registry entries are never rewritten')
    evidence = Evidence()
    if args.recorded:
        audit_path = root/RECORDED['audit'];fields = {k: v for k, v in RECORDED.items() if k != 'audit'}
    else:
        if not args.case_plan:
            parser.error('A declared case audit needs its case plan')
        audit_path = args.case_audit.resolve()/'summary.json'
        fields = from_case_plan(root, args.case_plan, json.loads(audit_path.read_text()))
    entry = dict(case_id=args.case_id, label=args.label, audit=str(audit_path), audit_sha256=sha(audit_path), **fields)
    case = verify_case(root, entry, evidence)
    # Informational copy for the UI; the worker re-derives and compares it exactly.
    entry['declaration'] = declaration(case)
    evidence.unchanged()
    registry['cases'].append(entry)
    path = root/REGISTRY;temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(registry, indent=2)+'\n');os.replace(temporary, path)
    print('registered', case['case_id'], case['audit_sha256'], 'source', case['source_hash'])


if __name__ == '__main__':
    main()
