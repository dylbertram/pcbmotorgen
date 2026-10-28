#!/usr/bin/env python3
"""Zero/reverse-speed and independent weak-limit checks for source-only motion.

Closed and slotted bodies are compared without assuming that removing metal
must lower dynamic loss. Weak-limit force changes sign between conductor-motion
and translating-PM frames. No accepted nonlinear backplane or winding claim.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_housing_motion_controls import load
from audit_current_closure import load as load_weak
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['forward','zero','reverse','slotted','slow','slotted-slow','weak-closure-work','weak-oracle']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous motion-limit audits')
    keys=['forward','zero','reverse','slotted','slow','slotted_slow']
    paths={name:getattr(args,name).resolve() for name in keys};records={name:load(path) for name,path in paths.items()}
    forward=records['forward'];reverse=records['reverse'];zero=records['zero'];checks={};failures=[]
    if any(r['model']!=forward['model'] or r['housing']!=forward['housing'] or r['request']['sigma']!=forward['request']['sigma'] for r in records.values()):
        raise ValueError('Different source models, housing envelope or conductivity')
    def check(label,error,limit):
        passed=bool(np.isfinite(error) and error<=limit);checks[label]={'error':float(error),'limit':float(limit),'passed':passed}
        if not passed:failures.append(label)
    if zero['request']['speed']!=0:raise ValueError('Zero control actually moves the source')
    check('zero heat/energy',abs(zero['joule_energy_j'])+abs(zero['reaction_energy_end_j']),0.)
    check('zero force',max(np.linalg.norm(row['housing_source_interaction_force_n']) for row in zero['steps']),0.)
    if forward['request']['speed']!=-reverse['request']['speed'] or forward['request']['steps']!=reverse['request']['steps'] or forward['mesh_sha256']!=reverse['mesh_sha256']:
        raise ValueError('Reverse control changed speed magnitude, time resolution or mesh')
    first=np.array([r['housing_source_interaction_force_n'] for r in forward['steps']]);second=np.array([r['housing_source_interaction_force_n'] for r in reverse['steps']])
    x=np.array([r['source_offset_m'] for r in forward['steps']]);y=np.array([r['source_offset_m'] for r in reverse['steps']])
    if not np.allclose(x,-y,rtol=1e-12,atol=1e-14):raise ValueError('Reverse source positions are not mirrored')
    reflected=first*np.array([-1.,1.,1.])
    check('reverse force curve',np.linalg.norm(second-reflected),max(1e-8,.02*np.linalg.norm(reflected)))
    for name in ['joule_energy_j','source_work_energy_j','reaction_energy_end_j']:
        check('reverse '+name,abs(reverse[name]/forward[name]-1),.02)
    weak=load_weak(args.weak_closure_work.resolve());oracle=json.loads(args.weak_oracle.read_text());completed_receipt(oracle)
    if oracle['status']!='passed-independent-finite-current-closure-low-rm-only' or oracle['failures'] or oracle['closure_report_sha256']!=sha(args.weak_closure_work/'summary.json'):
        raise ValueError('Independent weak-current oracle is incomplete, failed or mismatched')
    if weak['housing']!=forward['housing'] or weak['sigma_s_m']!=forward['request']['sigma']:
        raise ValueError('Weak reference uses different housing or conductivity')
    for label,shape in [('slow','closed'),('slotted_slow','slotted')]:
        trial=records[label]
        if trial['magnetic_reynolds_number']>.01:raise ValueError('Weak-limit comparison outside Rm<=0.01')
        row=min(trial['steps'],key=lambda record:abs(record['source_offset_m']))
        if abs(row['source_offset_m'])>1e-12:raise ValueError('Weak comparison must evaluate the same centred pose')
        reference=oracle['runs'][shape][-1];ratio=trial['request']['speed']/weak['speed_m_s']
        force=-ratio*np.array(reference['force_physical_n'])
        power=ratio**2*reference['joule_power_w']
        check(label+' independent FV force',np.linalg.norm(np.array(row['housing_source_interaction_force_n'])-force),max(1e-8,.05*np.linalg.norm(force)))
        check(label+' independent FV loss',abs(row['joule_power_w']/power-1),.05)
    slotted=records['slotted']
    if slotted['request']['slot']<=0 or forward['request']['slot']!=0:raise ValueError('Missing actual closed/slotted geometry contrast')
    result={'status':'failed' if failures else 'passed-finite-housing-motion-limits-source-only','scope':__doc__,
        'source_summary_sha256':{name:sha(path/'summary.json') for name,path in paths.items()},
        'weak_oracle_sha256':sha(args.weak_oracle),'checks':checks,'failures':failures,
        'slotted_over_closed_joule_energy':slotted['joule_energy_j']/forward['joule_energy_j'],
        'slot_removed_volume_fraction':1-slotted['conductor_volume_m3']/forward['conductor_volume_m3'],
        'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):result['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
