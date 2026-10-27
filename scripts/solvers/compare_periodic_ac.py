#!/usr/bin/env python3
"""Audit separate FE/spectral resolution axes before periodic tensor-AC agreement.

Retains the existing added-coil-factor absolute/relative gates and loss gates.
A new agreement does not rewrite failed historical FEMM cases, validate real
frequency-dependent MnZn, or qualify finite motor PWM/transients.
"""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

from audit_biased_ac import changes
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def read(work,status):
    report=json.loads((work/'summary.json').read_text())
    if not report.get('command_receipt'):raise ValueError('Missing whole-job receipt')
    completed_receipt(report)
    if report['status']!=status or report.get('failures')!=[]:raise ValueError('Incomplete or failed periodic study')
    for entry in report['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Changed archived periodic physics')
    return report


def fe_observables(report):
    reflection=np.array([complex(*phase['reflection']) for phase in report['ac']])
    loss=np.array([phase['joule_coefficient_w_m2_t2'] for phase in report['ac']])
    if reflection.shape!=(2,) or loss.shape!=(2,) or not np.isfinite(reflection).all() or not np.isfinite(loss).all() or np.any(loss<=0):
        raise ValueError('Invalid periodic AC observables')
    wave=math.pi/.006;sheet=.00002;u=wave*sheet
    self_weight=2*(u+math.expm1(-u))/(u*u)
    factor=(math.sinh(u/2)/(u/2))**2*float(np.mean(np.exp(-2*wave*np.array([sheet/2,.0008-sheet/2]))))/self_weight
    coil=1+factor*reflection
    return np.column_stack([coil.real,coil.imag]),loss


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fe-level',action='append',required=True,help='label=completed work directory')
    parser.add_argument('--spectral-work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous comparisons')
    order=['base','x','depth','depth_fine','air','wall','gap','source','x_fine','far','quadrature']
    paths=dict(item.split('=',1) for item in args.fe_level)
    if set(paths)!=set(order):parser.error('All independent FE resolution levels are required')
    paths={key:Path(value).resolve() for key,value in paths.items()}
    spectral=read(args.spectral_work,'passed-periodic-spectral-refinement-only')
    finite={key:read(path,'completed-periodic-tensor-ac-unqualified') for key,path in paths.items()}
    base=finite['base'];checks={};failures=[]
    for label,report in finite.items():
        if report['case']!=spectral['case'] or report['material']!=base['material'] or report['resolution']['frequency']!=spectral['frequency_hz']:
            raise ValueError('Different physical periodic cases')
        if report['bias']['relative_equation_residual']>1e-9 or any(p['relative_equation_residual']>1e-9 for p in report['ac']):
            raise ValueError('Unconverged bias or harmonic solve')
        if not report.get('mirror_symmetric_triangulation') or any(abs(complex(*p['cross_phase_reflection']))>1e-8 for p in report['ac']):
            raise ValueError('Symmetric periodic source has unqualified cross-phase coupling')
    axes={'x':'nx','depth':'cells','depth_fine':'cells','air':'air_cells','wall':'wall_cells','gap':'gap_cells','source':'source_modes','x_fine':'nx','quadrature':'bonus_order'}
    for prior,label in zip(order,order[1:]):
        a=finite[prior]['resolution'];b=finite[label]['resolution']
        changed={key for key in a if a[key]!=b[key]}
        if label=='far':
            if changed!={'far','air_cells'} or b['far']<=a['far'] or not np.isclose(a['far']/a['air_cells'],b['far']/b['air_cells'],rtol=1e-13):
                raise ValueError('Far-air expansion changed physical air spacing or other controls')
        elif changed!={axes[label]} or b[axes[label]]<=a[axes[label]]:
            raise ValueError('FE resolution controls were changed together or not refined')
        check=changes(fe_observables(finite[prior]),fe_observables(finite[label]))
        checks[label]=check
        if not check['passed']:failures.append('FE '+label+' refinement')
    final=spectral['levels']['gap']['spectral']
    spectral_values=(np.array(final['coil_factors_per_phase']),np.array(final['joule_coefficient_w_m2_t2']))
    agreement=changes(fe_observables(finite['quadrature']),spectral_values,relative=.05)
    checks['agreement']=agreement
    if not agreement['passed']:failures.append('FE/spectral agreement')
    report={'status':'failed' if failures else 'passed-independent-periodic-tensor-ac-only','scope':__doc__,
        'case':base['case'],'spectral_report_sha256':sha(args.spectral_work/'summary.json'),
        'fe_report_sha256':{label:sha(path/'summary.json') for label,path in paths.items()},
        'fe_initial_guesses':{label:record['initial_guess'] for label,record in finite.items() if 'initial_guess' in record},
        'checks':checks,'failures':failures,'historical_femm':'Original failed MnZn comparisons remain failed; missing Linux raw archives were not reconstructed by this new comparison.',
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_biased_ac.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
