#!/usr/bin/env python3
"""Two-point exterior source-field refinement only; not material/force evidence."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_finite_dc_controls import MIXED,load,validate_control
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def compare_fields(first,second):
    for report in [first,second]:
        if report.get('status')!='passed-two-exterior-source-points-only' or report.get('failures'):
            raise ValueError('Passing exterior pilots required')
        for key,limit in [('refinement_relative',.02),('agreement_relative',.05)]:
            values=np.asarray(report[key]);
            if not values.size or not np.isfinite(values).all() or np.max(values)>limit:raise ValueError('Original pilot gate failed')
    if first['points_m']!=second['points_m'] or first['trace_labels']!=second['trace_labels']:
        raise ValueError('Exact physical observation points must match; no interpolation')
    a=np.asarray(first['analytical_field_t']);b=np.asarray(second['analytical_field_t'])
    if a.shape!=b.shape or a.ndim!=2 or a.shape[1]!=3 or not len(a) or not np.isfinite([a,b]).all():raise ValueError('Finite vector fields required')
    currents=np.array([first['effective_loop_current_a'],second['effective_loop_current_a']])
    if not np.isfinite(currents).all() or np.min(currents)<=0:raise ValueError('Positive saved1V basis currents required')
    result={}
    for label,x,y in [('saved_1v_basis',a,b),('per_loop_a',a/currents[0],b/currents[1])]:
        relative=np.linalg.norm(x-y,axis=1)/np.maximum(np.linalg.norm(y,axis=1),1e-12)
        result[label]=dict(relative_difference=relative.tolist(),limit=.02,field_floor=1e-12,
            passed=bool(np.isfinite(relative).all() and np.max(relative)<=.02))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['first-work','second-work','first-report','second-report','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous exterior field controls')
    a=load(args.first_work,MIXED);b=load(args.second_work,MIXED);validate_control(a,b,'mesh')
    if a['request'].get('curvature_safety',2.)!=b['request'].get('curvature_safety',2.):raise ValueError('Curvature changed during spatial control')
    pilots=[];inputs={}
    for path,work,source in [(args.first_report,args.first_work,a),(args.second_report,args.second_work,b)]:
        path=path.resolve();work=work.resolve();report=json.loads(path.read_text());completed_receipt(report)
        if report['input_hashes'].get(str(work/'summary.json'))!=sha(work/'summary.json') or report['effective_loop_current_a']!=source['dc']['effective_loop_current_a']:
            raise ValueError('Pilot current-state provenance changed')
        for name,digest in report['input_hashes'].items():
            if sha(Path(name))!=digest:raise ValueError('Pilot physical source inputs changed')
        for entry in report['source_snapshots'].values():
            archived=(path.parent/entry['snapshot']).resolve()
            if not archived.is_relative_to(path.parent) or sha(archived)!=entry['sha256']:raise ValueError('Archived field implementation changed')
        inputs[str(path)]=sha(path);inputs.update(report['input_hashes']);pilots.append(report)
    checks=compare_fields(*pilots);passed=all(value['passed'] for value in checks.values())
    report=dict(status=('passed' if passed else 'failed')+'-two-exterior-point-spatial-control-only',scope=__doc__,checks=checks,
        points_m=pilots[0]['points_m'],input_hashes=inputs,
        normalization='Divide only by saved effective loop current to compare1A sources; no fitted scaling. Also check raw1V basis.',
        source_snapshots=capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_finite_dc_controls.py')]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Exterior refinement inputs changed')
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if not passed:raise ValueError('Exterior source-field spatial refinement fails2%gate')


if __name__=='__main__':main()
