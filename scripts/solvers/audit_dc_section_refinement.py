#!/usr/bin/env python3
"""Isolated DC local-section refinement, not full interior/field qualification."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_finite_dc_controls import MIXED,load,validate_control
from post_project_force import sha
from source_snapshot import capture


def compare_sections(first,second):
    status='passed-finite-dc-all-eligible-winding-sections-only'
    for report in [first,second]:
        if report.get('status')!=status or report.get('failures') or report.get('selection')!='all eligible':
            raise ValueError('Complete passing all-eligible active section reports required')
        if report.get('expected_sections')!=len(report['sections']):raise ValueError('Incomplete section inventory')
        if any(item.get('passed') is not True for item in report['sections']):raise ValueError('Individual original section gates must pass')
        if len({item['label'] for item in report['sections']})!=len(report['sections']):raise ValueError('Duplicate section labels')
    a={item['label']:item for item in first['sections']};b={item['label']:item for item in second['sections']}
    if not a or a.keys()!=b.keys():raise ValueError('Refinement section inventory changed')
    result=[]
    for label,x in a.items():
        y=b[label]
        for key in ['centre_m','normal','window_half_width_m','reference_per_loop_a']:
            if x[key]!=y[key]:raise ValueError('Refinement changed physical section or signed reference')
        values=np.array([x['current_per_loop_a'],y['current_per_loop_a'],x['area_m2'],y['area_m2']],dtype=float)
        if not np.isfinite(values).all() or min(values[2:])<=0:raise ValueError('Nonfinite or nonpositive section data')
        difference=abs(values[0]-values[1]);limit=max(1e-8,.02*max(abs(values[0]),abs(values[1])))
        area_difference=abs(values[2]/values[3]-1)
        result.append(dict(label=label,current_difference_per_loop_a=float(difference),current_limit_per_loop_a=float(limit),
            relative_area_difference=float(area_difference),area_limit=.02,passed=bool(difference<=limit and area_difference<=.02)))
    return result


def load_sections(path,work):
    path=Path(path).resolve();work=Path(work).resolve();report=json.loads(path.read_text());source=load(work,MIXED)
    receipt=json.loads(Path(report['command_receipt']).read_text())
    if receipt.get('status')!='completed' or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0:
        raise ValueError('Section audit has no completed whole-job receipt')
    if report['source_work']!=str(work) or report['source_summary_sha256']!=sha(work/'summary.json') or report['source_solution_sha256']!=source['solution_sha256']:
        raise ValueError('Section report source binding changed')
    if not report.get('source_snapshots'):raise ValueError('Section implementation archive required')
    for entry in report['source_snapshots'].values():
        archived=(path.parent/entry['snapshot']).resolve()
        if not archived.is_relative_to(path.parent) or sha(archived)!=entry['sha256']:raise ValueError('Archived section implementation changed')
    return report,source


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['first-work','second-work','first-report','second-report','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--kind',choices=['mesh','port'],required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous local refinement evidence')
    first,a=load_sections(args.first_report,args.first_work);second,b=load_sections(args.second_report,args.second_work)
    validate_control(a,b,args.kind)
    if a['request'].get('curvature_safety',2.)!=b['request'].get('curvature_safety',2.):raise ValueError('Curvature changed during isolated control')
    inputs={str(path.resolve()):sha(path) for path in [args.first_report,args.second_report,args.first_work/'summary.json',args.second_work/'summary.json']}
    sections=compare_sections(first,second);failures=[value['label'] for value in sections if not value['passed']]
    report=dict(status=('failed' if failures else 'passed')+'-local-dc-section-refinement-only',scope=__doc__,kind=args.kind,
        current_relative_gate=.02,current_floor_per_loop_a=1e-8,sections=sections,failures=failures,input_hashes=inputs,
        source_snapshots=capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_finite_dc_controls.py')]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Local refinement inputs changed')
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if failures:raise ValueError('Original2%local section refinement gate failed')


if __name__=='__main__':main()
