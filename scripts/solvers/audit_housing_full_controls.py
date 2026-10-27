#!/usr/bin/env python3
"""Full-entry/exit and slot-specific discretization checks for source-only motion.

Check the full stored-energy trajectory as well as its endpoint. The trajectory
prevents a nearly zero end value from hiding unresolved internal transients.
Integral heat/work, force history and both energy checks retain the 2% gate.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_housing_motion_controls import load,control_axis
from post_project_force import sha
from source_snapshot import capture


def change(a,b):
    checks={}
    for key in ['joule_energy_j','source_work_energy_j']:
        error=abs(a[key]/b[key]-1);checks[key]={'relative_change':error,'passed':bool(error<=.02)}
    ta=np.array([r['time_mid_s'] for r in a['steps']]);tb=np.array([r['time_mid_s'] for r in b['steps']])
    force_a=np.array([r['housing_source_interaction_force_n'] for r in a['steps']]);force_b=np.array([r['housing_source_interaction_force_n'] for r in b['steps']])
    if ta.min()<tb.min() or ta.max()>tb.max():raise ValueError('Do not extrapolate refinement force histories')
    target=np.column_stack([np.interp(ta,tb,force_b[:,i]) for i in range(3)])
    absolute=float(np.linalg.norm(force_a-target));limit=max(1e-8,.02*float(np.linalg.norm(target)))
    checks['force_curve']={'absolute_l2_change_n':absolute,'limit_n':limit,'passed':absolute<=limit}
    ea=np.array([r['reaction_energy_end_j'] for r in a['steps']]);eb=np.array([r['reaction_energy_end_j'] for r in b['steps']])
    end_a=ta+a['profile']['dt_s']/2;end_b=tb+b['profile']['dt_s']/2
    aligned=np.interp(end_a,end_b,eb)
    error=float(np.linalg.norm(ea-aligned)/max(np.linalg.norm(aligned),1e-30))
    checks['stored_energy_history']={'relative_l2_change':error,'passed':error<=.02}
    end_error=float(abs(ea[-1]/eb[-1]-1)) if eb[-1] else 0. if ea[-1]==0 else None
    checks['end_energy']={'first_j':float(ea[-1]),'second_j':float(eb[-1]),
        'relative_change':end_error,'passed':bool(end_error is not None and end_error<=.02),
        'note':'Endpoint and complete stored-energy history must both pass.'}
    return {'checks':checks,'passed':bool(all(value['passed'] for value in checks.values() if 'passed' in value))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    names=['closed','slotted','closed-time','slotted-time','closed-mesh','slotted-mesh']
    for name in names:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier full-stroke control audits')
    paths={name:getattr(args,name.replace('-','_')).resolve() for name in names};records={name:load(path) for name,path in paths.items()}
    checks={};failures=[]
    for shape in ['closed','slotted']:
        for suffix,axis in [('time','time'),('mesh','mesh')]:
            a=records[shape];b=records[shape+'-'+suffix];control_axis(a,b,axis)
            result=change(a,b);label=shape+'-'+axis;checks[label]=result
            if not result['passed']:failures.append(label)
    output={'status':'failed' if failures else 'passed-full-entry-exit-and-slot-controls-source-only','scope':__doc__,
        'source_summary_sha256':{name:sha(path/'summary.json') for name,path in paths.items()},'gate':.02,
        'checks':checks,'failures':failures,'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
