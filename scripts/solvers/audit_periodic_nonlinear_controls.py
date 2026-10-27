#!/usr/bin/env python3
"""One isolated nonlinear periodic refinement, after absolute-state audits.

Uses the recorded 2% refinement gates and existing added-factor near-zero
floors. A pass is only this numerical axis at one phase and amplitude, not an
amplitude envelope or real winding/current/PWM rating.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_biased_ac import changes
from compare_periodic_nonlinear import observable,load,audit
from post_project_force import sha
from source_snapshot import capture


def normalized(record):
    if record['status']=='completed-independent-periodic-nonlinear-transient-unqualified':
        request=record['request'];resolution=dict(record['source_resolution'],steps_per_period=request['steps_per_period'])
        material=record['material'];physical=[material['thickness_m'],material['mu_initial'],material['saturation_polarization_t'],material['conductivity_s_m'],resolution['frequency']]
        return {'backend':'FE','resolution':resolution,'physical':physical,'fraction':request['fraction'],'phase':request['phase'],
            'observables':observable(record['reflection'],record['joule_coefficient_w_m2_t2'])}
    if record['status']=='completed-periodic-nonlinear-transient-unqualified':
        request=record['request'];resolution={k:request[k] for k in ['cells','modes','samples','wall_cells','gap_cells','steps_per_period']}
        return {'backend':'spectral','resolution':resolution,'physical':[request[k] for k in ['thickness','mu','bsat','layer_conductivity','frequency']],
            'fraction':request['fraction'],'phase':request['phase'],
            'observables':observable(record['result']['reflection'],record['result']['joule_coefficient_w_m2_t2'])}
    raise ValueError('Unsupported or failed nonlinear periodic trial')


def control_axis(a,b,axis):
    for key in ['backend','physical','fraction','phase']:
        if a[key]!=b[key]:raise ValueError('Different nonlinear periodic physics, phase, amplitude or backend')
    first=a['resolution'];second=b['resolution'];changed={k for k in set(first)|set(second) if first.get(k)!=second.get(k)}
    expected={'time':'steps_per_period','lateral':'nx','depth':'cells','modes':'source_modes' if a['backend']=='FE' else 'modes',
        'angles':'samples','wall':'wall_cells','gap':'gap_cells','air':'air_cells','quadrature':'bonus_order'}.get(axis)
    if axis=='domain':
        if changed!={'far','air_cells'} or second['far']<=first['far'] or not np.isclose(first['far']/first['air_cells'],second['far']/second['air_cells'],rtol=1e-13):
            raise ValueError('Nonlinear exterior-domain control changed physical air spacing or other axes')
    elif expected is None or changed!={expected} or second[expected]<=first[expected]:
        raise ValueError('Nonlinear controls changed together, or did not refine the declared axis')


def read_trial(work,proof):
    raw=json.loads((work/'summary.json').read_text());status=raw['status'];record=load(work,status)
    if status=='completed-independent-periodic-nonlinear-transient-unqualified':
        audit(proof,'passed-ngsolve-midpoint-trace-equations-only',work,work/'last-two-periods.npz')
    elif status=='completed-periodic-nonlinear-transient-unqualified':
        audit(proof,'passed-midpoint-trace-equations-only',work,Path(record['result']['trace']))
    else:raise ValueError('Failed/incomplete nonlinear trial')
    return normalized(record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['coarse','fine','coarse-audit','fine-audit','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--axis',choices=['time','lateral','depth','modes','angles','wall','gap','air','domain','quadrature'],required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve all nonlinear refinement comparisons')
    a=read_trial(args.coarse,args.coarse_audit);b=read_trial(args.fine,args.fine_audit);control_axis(a,b,args.axis)
    result=changes(a['observables'],b['observables'],relative=.02)
    output={'status':'passed-nonlinear-periodic-'+args.axis+'-control-only' if result['passed'] else 'failed',
        'scope':__doc__,'axis':args.axis,'backend':a['backend'],'fraction':a['fraction'],'phase':a['phase'],'result':result,
        'input_hashes':{str(p):sha(p) for p in [args.coarse/'summary.json',args.fine/'summary.json',args.coarse_audit,args.fine_audit]},
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_biased_ac.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if not result['passed']:raise SystemExit('Nonlinear periodic refinement failed')


if __name__=='__main__':main()
