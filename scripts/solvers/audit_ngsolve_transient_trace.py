#!/usr/bin/env python3
"""Reassemble nonlinear FE midpoint equations from absolute archived states.

Checks trace integrity, settlement, source work, heat and reflected waveform.
This is an internal equation audit, not independent nonlinear physics or an
amplitude-envelope, finite-winding or PWM qualification.
"""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from ngsolve_periodic_ac import energy,source_modes,symmetric_triangle_rule,MU0
from ngsolve_periodic_transient import sparse
from post_project_force import sha
from solver_threads import add_thread_option,runtime_metadata,threaded_main
from source_snapshot import capture


def trace_arrays(raw,steps,dofs,dt,amplitude,phase):
    previous=np.asarray(raw['previous']);mid=np.asarray(raw['midpoints']);following=np.asarray(raw['next']);bias=np.asarray(raw['equilibrium'])
    if previous.shape!=(2*steps,dofs) or mid.shape!=previous.shape or following.shape!=previous.shape or bias.shape!=(dofs,):
        raise ValueError('Wrong FE absolute trace dimensions')
    if not all(np.isfinite(x).all() for x in [previous,mid,following,bias]):raise ValueError('Nonfinite FE absolute trace')
    for key,expected in [('dt',dt),('amplitude',amplitude),('phase',phase)]:
        if not np.isclose(float(raw[key]),expected,rtol=1e-13,atol=0.):raise ValueError('FE trace header differs: '+key)
    if not np.array_equal(previous[1:],following[:-1]):raise ValueError('Discontinuous FE trace')
    if not np.allclose(2*mid,previous+following,rtol=1e-13,atol=1e-16):raise ValueError('FE states do not satisfy midpoint identity')
    return previous,mid,following,bias


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--source-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);add_thread_option(parser);args=parser.parse_args()
    work=args.work.resolve();origin=args.source_work.resolve()
    if args.output.exists():parser.error('Preserve previous FE trace audits')
    report=json.loads((work/'summary.json').read_text());source=json.loads((origin/'summary.json').read_text())
    completed_receipt(report);completed_receipt(source)
    if report['status']!='completed-independent-periodic-nonlinear-transient-unqualified' or report['failures'] or source['status']!='completed-periodic-tensor-ac-unqualified' or source['failures']:
        raise ValueError('Failed/incomplete FE trajectory or source cannot be qualified')
    if sha(origin/'summary.json')!=report['source_summary_sha256'] or sha(origin/'bias.sol')!=report['source_bias_sha256'] or sha(origin/'mesh.vol')!=source['mesh_sha256']:
        raise ValueError('FE source bias or mesh changed')
    trace=work/'last-two-periods.npz'
    if sha(trace)!=report['trace_sha256']:raise ValueError('FE absolute trace changed')
    for filename in ['ngsolve_periodic_ac.py','ngsolve_periodic_transient.py']:
        entry=next(v for k,v in report['source_snapshots'].items() if Path(k).name==filename)
        if sha(work/entry['snapshot'])!=entry['sha256'] or sha(Path(__file__).with_name(filename))!=entry['sha256']:
            raise ValueError('FE trace and audited equation definitions differ')
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('FE trace engine version differs')
    resolution=source['resolution'];material=source['material'];request=report['request'];steps=request['steps_per_period']
    if report['completed_steps']%steps or report['completed_steps']<4*steps or report['completed_steps']>request['periods']*steps:
        raise ValueError('FE trace completed-period count is inconsistent')
    frequency=resolution['frequency'];omega=2*math.pi*frequency;dt=1/(frequency*steps);period=.012
    mesh=ng.Mesh(str(origin/'mesh.vol'));fes=ng.Periodic(ng.H1(mesh,order=2,dirichlet='far_top|far_bottom'))
    free=np.array(fes.FreeDofs(),dtype=bool);trial,test=fes.TnT();state=ng.GridFunction(fes);bias=ng.GridFunction(fes);bias.Load(str(origin/'bias.sol'))
    rule=symmetric_triangle_rule(ng,4+resolution['bonus_order']);measure=lambda name:ng.dx(definedon=mesh.Materials(name),intrules={ng.ET.TRIG:rule})
    k,incident=source_modes(resolution['source_modes']);bx=ng.CoefficientFunction(0.);bz=ng.CoefficientFunction(0.)
    for wave,b in zip(k,incident):bx+=-b*ng.sin(wave*ng.x)*ng.exp(-wave*ng.y);bz+=b*ng.cos(wave*ng.x)*ng.exp(-wave*ng.y)
    bx=ng.CacheCF(bx.Compile());bz=ng.CacheCF(bz.Compile());gx,gz=ng.grad(trial)[1],ng.grad(trial)[0]
    density=(energy(ng,bx+gx,bz+gz,material['mu_initial'],material['saturation_polarization_t'])-(bx*gx+bz*gz)/MU0).Compile()
    static=ng.BilinearForm(fes,symmetric=True);static+=ng.Variation(density*measure('plate'))
    static+=ng.Variation((ng.InnerProduct(ng.grad(trial),ng.grad(trial))/(2*MU0))*measure('air|wall'))
    mass=ng.BilinearForm(fes,symmetric=True);mass+=(material['conductivity_s_m']*trial*test)*measure('plate');mass+=(25e6*trial*test)*measure('wall');mass.Assemble()
    matrix=sparse(mass.mat,fes.ndof);shape=ng.sin(k[0]*ng.x) if request['phase']==0 else ng.cos(k[0]*ng.x)
    forcing=ng.LinearForm(fes);forcing+=(2/MU0*shape*test)*ng.ds('source',bonus_intorder=resolution['bonus_order']);forcing.Assemble()
    f=np.array(forcing.vec.FV().NumPy());amplitude=abs(incident[0])*request['fraction'];residual=state.vec.CreateVector()
    static.Apply(state.vec,residual);scale=float(np.linalg.norm(residual.FV().NumPy()[free]));static.Apply(bias.vec,residual)
    bias_residual=float(np.linalg.norm(residual.FV().NumPy()[free]))/scale
    if bias_residual>1e-9:raise ValueError('Archived bias fails the nonlinear FE equation')
    losses=[];works=[];top=[];maximum=0.
    with np.load(trace,allow_pickle=False) as raw:
        previous,mid,following,equilibrium=trace_arrays(raw,steps,fes.ndof,dt,amplitude,request['phase'])
        if not np.array_equal(equilibrium,bias.vec.FV().NumPy()):raise ValueError('Absolute FE trace bias differs from the solved source')
        for i,(old,centre,new) in enumerate(zip(previous,mid,following)):
            derivative=(new-old)/dt;drive=amplitude*np.sin(omega*(i+.5)*dt);state.vec.FV().NumPy()[:]=centre
            static.Apply(state.vec,residual);equation=residual.FV().NumPy()+matrix@derivative-drive*f
            maximum=max(maximum,float(np.linalg.norm(equation[free]))/scale)
            losses.append(float(derivative@(matrix@derivative))/period);works.append(float(drive*np.dot(f,derivative))/period)
            top.append(float(ng.Integrate((state-bias)*shape,mesh,definedon=mesh.Boundaries('source'),order=8))*2/period)
        if maximum>1e-10:raise ValueError('Reassembled full nonlinear FE midpoint equation failed')
        for key,actual in [('loss',losses),('source_work',works),('top',top)]:
            if not np.allclose(actual,raw[key],rtol=1e-9,atol=1e-18):raise ValueError('FE trace observable differs: '+key)
    ripple=mid-equilibrium;settlement=float(np.linalg.norm(ripple[steps:]-ripple[:steps])/np.linalg.norm(ripple[steps:]))
    loss=float(np.mean(losses[-steps:])/amplitude**2);power=float(np.mean(works[-steps:])/amplitude**2)
    times=(np.arange(steps)+.5)*dt;phasor=2*np.mean(np.array(top[-steps:])*np.exp(-1j*omega*times));reflection=k[0]*phasor/(-1j*amplitude)-1
    if settlement>1e-5 or loss<=0 or abs(power/loss-1)>.02:raise ValueError('Recomputed FE settlement or energy gate failed')
    if not np.allclose([reflection.real,reflection.imag],report['reflection'],rtol=1e-9,atol=1e-12) or not np.isclose(loss,report['joule_coefficient_w_m2_t2'],rtol=1e-9):
        raise ValueError('FE summary differs from absolute trace')
    if sha(trace)!=report['trace_sha256']:raise ValueError('FE trace changed during audit')
    output={'status':'passed-ngsolve-midpoint-trace-equations-only','scope':__doc__,'execution':runtime_metadata(),
        'summary_sha256':sha(work/'summary.json'),'source_summary_sha256':sha(origin/'summary.json'),'trace_sha256':sha(trace),
        'proof':{'maximum_recomputed_relative_equation_residual':maximum,'checked_steps':2*steps,'bias_relative_residual':bias_residual,
            'settlement_relative_change':settlement,'power_relative_balance':abs(power/loss-1),'joule_coefficient_w_m2_t2':loss,'reflection':[reflection.real,reflection.imag]},
        'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':threaded_main(main)
