#!/usr/bin/env python3
"""Independent nonlinear FE/spectral agreement at one amplitude and phase.

Both full nonlinear midpoint implementations must finish and pass absolute-state
equation audits first. This comparison alone establishes neither independent
spatial/time convergence nor an amplitude envelope, actual winding or PWM.
Analytical PM source and provisional reversible material law are shared.
"""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

from audit_biased_ac import changes
from compare_reduced_fields import completed_receipt
from ngsolve_periodic_ac import source_modes
from post_project_force import sha
from source_snapshot import capture
from spectral_incremental import FullPhasePlate


def observable(reflection,loss):
    reflection=complex(*reflection);loss=float(loss)
    if not np.isfinite([reflection.real,reflection.imag,loss]).all() or loss<=0:raise ValueError('Invalid nonlinear periodic observable')
    wave=math.pi/.006;sheet=.00002;u=wave*sheet
    self_weight=2*(u+math.expm1(-u))/(u*u)
    factor=(math.sinh(u/2)/(u/2))**2*float(np.mean(np.exp(-2*wave*np.array([sheet/2,.0008-sheet/2]))))/self_weight
    coil=1+factor*reflection
    return np.array([[coil.real,coil.imag]]),np.array([loss])


def load(work,status):
    report=json.loads((work/'summary.json').read_text());completed_receipt(report)
    if report['status']!=status or report['failures']:raise ValueError('Incomplete or failed nonlinear periodic trial')
    for entry in report['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Archived nonlinear physics changed')
    return report


def audit(path,status,work,trace):
    proof=json.loads(path.read_text());completed_receipt(proof)
    if proof['status']!=status or proof['summary_sha256']!=sha(work/'summary.json') or proof['trace_sha256']!=sha(trace):
        raise ValueError('Missing or mismatched nonlinear absolute-state audit')


def same_case(fe,source,spectral):
    a=fe['request'];b=spectral['request'];material=fe['material']
    for name in ['fraction','phase']:
        if a[name]!=b[name]:raise ValueError('Different nonlinear phase or amplitude')
    pairs=[(material['thickness_m'],b['thickness']),(material['mu_initial'],b['mu']),
        (material['saturation_polarization_t'],b['bsat']),(material['conductivity_s_m'],b['layer_conductivity']),
        (fe['source_resolution']['frequency'],b['frequency'])]
    if any(x!=y for x,y in pairs):raise ValueError('Different nonlinear physical materials or frequency')
    if source['resolution']!=fe['source_resolution'] or source['material']!=material:raise ValueError('Changed FE source metadata')
    if source['resolution']['source_modes']!=b['modes']:raise ValueError('Different prescribed PM source truncation')
    plate=FullPhasePlate(b['thickness'],b['mu'],b['bsat'],b['cells'],b['modes'],b['samples'])
    k,incident=source_modes(source['resolution']['source_modes'])
    if not np.allclose(k,plate.k[:b['modes']],rtol=1e-13,atol=0.) or not np.allclose(incident,plate.incident[:b['modes']],rtol=1e-13,atol=1e-15):
        raise ValueError('Independent nonlinear prescribed PM sources differ')
    for name,value in [('gap_cells',b['gap_cells']),('wall_cells',b['wall_cells'])]:
        if value<1:raise ValueError('Unresolved finite conductor gap or depth')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['fe-work','fe-source-work','fe-audit','spectral-work','spectral-audit','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous independent nonlinear comparisons')
    fe=load(args.fe_work,'completed-independent-periodic-nonlinear-transient-unqualified')
    spectral=load(args.spectral_work,'completed-periodic-nonlinear-transient-unqualified')
    source=load(args.fe_source_work,'completed-periodic-tensor-ac-unqualified');same_case(fe,source,spectral)
    if sha(args.fe_source_work/'summary.json')!=fe['source_summary_sha256']:raise ValueError('Different FE source summary')
    audit(args.fe_audit,'passed-ngsolve-midpoint-trace-equations-only',args.fe_work,args.fe_work/'last-two-periods.npz')
    audit(args.spectral_audit,'passed-midpoint-trace-equations-only',args.spectral_work,Path(spectral['result']['trace']))
    result=spectral['result']
    first=observable(fe['reflection'],fe['joule_coefficient_w_m2_t2']);second=observable(result['reflection'],result['joule_coefficient_w_m2_t2'])
    agreement=changes(first,second,relative=.05)
    output={'status':'passed-independent-nonlinear-periodic-single-amplitude-only' if agreement['passed'] else 'failed',
        'scope':__doc__,'request':{'fraction':fe['request']['fraction'],'phase':fe['request']['phase'],'frequency_hz':fe['source_resolution']['frequency']},
        'agreement':agreement,'fe_reflection':fe['reflection'],'spectral_reflection':result['reflection'],
        'input_hashes':{str(p):sha(p) for p in [args.fe_work/'summary.json',args.fe_source_work/'summary.json',args.spectral_work/'summary.json',args.fe_audit,args.spectral_audit]},
        'scope_not_achieved':['independent nonlinear space/time refinement','amplitude envelope','finite geometry/current/PWM','measured frequency-dependent material law'],
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_biased_ac.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if not agreement['passed']:raise SystemExit('Independent nonlinear periodic agreement failed')


if __name__=='__main__':main()
