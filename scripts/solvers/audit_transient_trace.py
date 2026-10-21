#!/usr/bin/env python3
"""Recompute last-two-period midpoint equations from absolute archived states.

This checks internal trace consistency, not an independent nonlinear solver,
spatial convergence, an accepted amplitude envelope or a real motor rating.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture
from spectral_incremental import FullPhasePlate
from spectral_transient import Transient,MU0

PHYSICS=['spectral_transient.py','spectral_biased_ac.py','spectral_incremental.py','spectral_plate.py','vector_harmonic_screen.py']


def audit_states(request,result,raw):
    plate=FullPhasePlate(request['thickness'],request['mu'],request['bsat'],request['cells'],request['modes'],request['samples'])
    model=Transient(plate,wall_cells=request['wall_cells'],gap_cells=request['gap_cells'],layer_conductivity=request['layer_conductivity'])
    previous=np.asarray(raw['previous']);mid=np.asarray(raw['midpoints']);following=np.asarray(raw['next']);equilibrium=np.asarray(raw['equilibrium'])
    steps=request['steps_per_period'];dt=1/(request['frequency']*steps);amplitude=abs(plate.incident[0])*request['fraction']
    if previous.shape!=(2*steps,model.size) or mid.shape!=previous.shape or following.shape!=previous.shape or equilibrium.shape!=(model.size,):
        raise ValueError('Wrong absolute trace dimensions')
    if not all(np.isfinite(value).all() for value in [previous,mid,following,equilibrium]):raise ValueError('Nonfinite absolute trace')
    for key,expected in [('dt',dt),('amplitude',amplitude),('phase',request['phase']),('steps_per_period',steps),('periods',request['periods'])]:
        if not np.isclose(float(raw[key]),expected,rtol=1e-13,atol=0.):raise ValueError('Trace header differs from physical request: '+key)
    if not np.array_equal(previous[1:],following[:-1]):raise ValueError('Discontinuous time trace')
    if not np.allclose(2*mid,previous+following,rtol=1e-13,atol=1e-16):raise ValueError('States do not satisfy midpoint identity')
    bias_residual=float(np.linalg.norm(model.evaluate(equilibrium,False)[1])/model.scale)
    if bias_residual>1e-9:raise ValueError('Archived attached-tail equilibrium is unconverged')
    index=request['phase']*request['modes'];omega=2*np.pi*request['frequency'];loss=[];work=[];maximum=0.
    for i,(old,centre,new) in enumerate(zip(previous,mid,following)):
        derivative=(new-old)/dt
        forcing=np.zeros(model.size);forcing[index]=amplitude/MU0*np.sin(omega*(i+.5)*dt)
        gradient=model.evaluate(centre,False)[1]
        residual=gradient+model.mass@derivative-forcing
        maximum=max(maximum,float(np.linalg.norm(residual)/model.scale))
        loss.append(float(derivative@(model.mass@derivative)));work.append(float(forcing@derivative))
    if maximum>1e-10:raise ValueError('Recomputed nonlinear midpoint equation failed')
    if not np.allclose(loss,raw['loss'],rtol=1e-10,atol=1e-18) or not np.allclose(work,raw['source_work'],rtol=1e-10,atol=1e-18):
        raise ValueError('Archived power samples differ from recomputed states/source')
    ripple=mid-equilibrium;settled=float(np.linalg.norm(ripple[steps:]-ripple[:steps])/np.linalg.norm(ripple[steps:]))
    joule=float(np.mean(loss[-steps:])/amplitude**2);source=float(np.mean(work[-steps:])/amplitude**2)
    if settled>1e-5 or joule<=0 or abs(source/joule-1)>.02:raise ValueError('Periodic settlement or source-work/Joule gate failed')
    time=(np.arange(steps)+.5)*dt;phasor=2*np.mean(ripple[-steps:,index]*np.exp(-1j*omega*time))
    reflection=plate.k[0]*phasor/(-1j*amplitude)-1
    if not np.allclose([reflection.real,reflection.imag],result['reflection'],rtol=1e-10,atol=1e-12):
        raise ValueError('Reported reflection differs from raw states')
    if not np.isclose(joule,result['joule_coefficient_w_m2_t2'],rtol=1e-10):raise ValueError('Reported loss differs from raw states')
    return {'maximum_recomputed_relative_equation_residual':maximum,'attached_tail_equilibrium_residual':bias_residual,
        'periodic_settlement_relative_change':settled,'relative_power_balance_error':abs(source/joule-1),
        'reflection':[reflection.real,reflection.imag],'joule_coefficient_w_m2_t2':joule,'checked_steps':2*steps}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('Preserve previous trace audits')
    report=json.loads((work/'summary.json').read_text())
    if not report.get('command_receipt'):raise ValueError('Missing whole-trial supervisor receipt')
    completed_receipt(report)
    if report['status']!='completed-periodic-nonlinear-transient-unqualified' or report['failures']:
        raise ValueError('Failed/incomplete nonlinear trial cannot be audited as accepted evidence')
    archived={Path(name).name:entry for name,entry in report['source_snapshots'].items()}
    for name in PHYSICS:
        entry=archived[name]
        if sha(work/entry['snapshot'])!=entry['sha256'] or sha(Path(__file__).with_name(name))!=entry['sha256']:
            raise ValueError('Archived/current nonlinear physics differ')
    result=report['result'];trace=Path(result['trace'])
    if sha(trace)!=result['trace_sha256']:raise ValueError('Raw transient trace changed')
    with np.load(trace,allow_pickle=False) as raw:proof=audit_states(report['request'],result,raw)
    output={'status':'passed-midpoint-trace-equations-only','scope':__doc__,'proof':proof,
        'summary_sha256':sha(work/'summary.json'),'trace_sha256':sha(trace),
        'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
