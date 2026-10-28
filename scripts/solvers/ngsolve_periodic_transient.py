#!/usr/bin/env python3
"""Independent nonlinear 2D FE midpoint ripple check about a static PM bias.

The harmonic orbit initializes only the state. Every step evaluates the full
two-slope magnetic energy and its automatic tangent. No frozen/secant mu is
used in time stepping. This is periodic/infinite-depth physics, not a finite
winding, arbitrary PWM, moving housing or measured material-loss model.
"""
import argparse
import ast
import json
import math
import os
from pathlib import Path
import time
from collections import deque

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from compare_reduced_fields import completed_receipt
from ngsolve_periodic_ac import energy,source_modes,symmetric_triangle_rule,MU0
from post_project_force import sha
from source_snapshot import capture
from solver_threads import add_thread_option,runtime_metadata,threaded_main


def sparse(matrix,size):
    rows,columns,values=matrix.COO()
    return coo_matrix((np.array(values),(np.array(rows),np.array(columns))),shape=(size,size)).tocsc()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--fraction',type=float,default=.001);parser.add_argument('--phase',type=int,choices=[0,1],default=0)
    parser.add_argument('--steps',type=int,default=64);parser.add_argument('--periods',type=int,default=8)
    parser.add_argument('--settle-early',action='store_true',help='after >=4 periods, stop only when the unchanged last-two-period gate passes')
    parser.add_argument('--explicit-tangent',action='store_true',help='reassemble the equivalent full constitutive gradient/tangent at each nonlinear iterate')
    parser.add_argument('--reuse-newton-factor',action='store_true',help='solve each updated Jacobian by checked CG with a reusable sparse-factor preconditioner')
    parser.add_argument('--stable-residual',action='store_true',help='subtract midpoint/previous states before applying the conducting mass; same nonlinear equations')
    add_thread_option(parser)
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous independent FE transient trials')
    if not np.isfinite(args.fraction) or args.fraction<=0 or args.steps<32 or args.periods<4:
        parser.error('Positive finite amplitude, >=32 steps and >=4 periods required')
    source=json.loads((origin/'summary.json').read_text());completed_receipt(source)
    if source['status']!='completed-periodic-tensor-ac-unqualified' or source['failures'] or not source.get('mirror_symmetric_triangulation'):
        raise ValueError('Need a completed reflection-symmetric periodic bias/AC source')
    if sha(origin/'mesh.vol')!=source['mesh_sha256']:raise ValueError('Source mesh changed')
    archived=next(origin/item['snapshot'] for name,item in source['source_snapshots'].items() if Path(name).name=='ngsolve_periodic_ac.py')
    def functions(path):return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef)}
    original=functions(archived);current=functions(Path(__file__).with_name('ngsolve_periodic_ac.py'))
    if any(original.get(key)!=current.get(key) for key in ['energy','source_modes','symmetric_triangle_rule']):
        raise ValueError('Static source and transient constitutive/source/quadrature definitions differ')
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('Reload the bias with its pinned NGSolve version')
    resolution=source['resolution'];material=source['material'];frequency=resolution['frequency'];omega=2*math.pi*frequency
    dt=1/(frequency*args.steps);period=.012;mu=material['mu_initial'];bsat=material['saturation_polarization_t']
    sigma=material['conductivity_s_m'];thickness=material['thickness_m']
    mesh=ng.Mesh(str(origin/'mesh.vol'));fes=ng.Periodic(ng.H1(mesh,order=2,dirichlet='far_top|far_bottom'))
    equilibrium=ng.GridFunction(fes);equilibrium.Load(str(origin/'bias.sol'));bias_sha=sha(origin/'bias.sol')
    free=np.array(fes.FreeDofs(),dtype=bool);trial,test=fes.TnT()
    rule=symmetric_triangle_rule(ng,4+resolution['bonus_order'])
    measure=lambda name:ng.dx(definedon=mesh.Materials(name),intrules={ng.ET.TRIG:rule})
    k,incident=source_modes(resolution['source_modes']);bx=ng.CoefficientFunction(0.);bz=ng.CoefficientFunction(0.)
    for wave,b in zip(k,incident):
        bx+=-b*ng.sin(wave*ng.x)*ng.exp(-wave*ng.y);bz+=b*ng.cos(wave*ng.x)*ng.exp(-wave*ng.y)
    bx=ng.CacheCF(bx.Compile());bz=ng.CacheCF(bz.Compile())
    gx,gz=ng.grad(trial)[1],ng.grad(trial)[0]
    density=(energy(ng,bx+gx,bz+gz,mu,bsat)-(bx*gx+bz*gz)/MU0).Compile()
    def magnetic_form():
        form=ng.BilinearForm(fes,symmetric=True)
        form+=ng.Variation(density*measure('plate'))
        form+=ng.Variation((ng.InnerProduct(ng.grad(trial),ng.grad(trial))/(2*MU0))*measure('air|wall'))
        return form
    static=magnetic_form();stepping=magnetic_form()
    stepping+=ng.Variation((sigma/dt*trial**2)*measure('plate'))
    stepping+=ng.Variation((25e6/dt*trial**2)*measure('wall'))
    mass=ng.BilinearForm(fes,symmetric=True)
    mass+=(sigma*trial*test)*measure('plate');mass+=(25e6*trial*test)*measure('wall');mass.Assemble()
    if args.explicit_tangent:
        from periodic_nonlinear_operator import ExplicitNonlinearPlate
        static=ExplicitNonlinearPlate(ng,fes,mesh,bx,bz,mu,bsat,sigma,rule)
        stepping=ExplicitNonlinearPlate(ng,fes,mesh,bx,bz,mu,bsat,sigma,rule,2/dt)
    shape=ng.sin(k[0]*ng.x) if args.phase==0 else ng.cos(k[0]*ng.x)
    forcing=ng.LinearForm(fes);forcing+=(2/MU0*shape*test)*ng.ds('source',bonus_intorder=resolution['bonus_order']);forcing.Assemble()
    zero=ng.GridFunction(fes);residual=zero.vec.CreateVector();static.Apply(zero.vec,residual)
    reference=float(np.linalg.norm(residual.FV().NumPy()[free]))
    static.Apply(equilibrium.vec,residual);bias_residual=float(np.linalg.norm(residual.FV().NumPy()[free]))/reference
    if bias_residual>1e-9:raise ValueError('Loaded bias does not satisfy the independent transient equations')
    static.AssembleLinearization(equilibrium.vec)
    kmat=sparse(static.mat,fes.ndof);mmat=sparse(mass.mat,fes.ndof)
    amplitude=abs(incident[0])*args.fraction;discrete=2/dt*math.tan(omega*dt/2)
    orbit=spsolve((kmat+1j*discrete*mmat)[free][:,free],-1j*amplitude*np.array(forcing.vec.FV().NumPy()[free]))
    previous=ng.GridFunction(fes);previous.vec.data=equilibrium.vec
    previous.vec.FV().NumPy()[free]+=orbit.real/math.cos(omega*dt/2)
    midpoint=ng.GridFunction(fes);candidate=ng.GridFunction(fes);rhs=zero.vec.CreateVector();direction=zero.vec.CreateVector();next_vector=zero.vec.CreateVector()
    work.mkdir(parents=True);snapshots=capture(work,[Path(__file__),Path(__file__).with_name('ngsolve_periodic_ac.py'),Path(__file__).with_name('solver_threads.py'),Path(__file__).with_name('periodic_nonlinear_operator.py'),Path(__file__).with_name('newton_factor.py'),Path(__file__).with_name('midpoint_residual.py')])
    report={'status':'running','scope':__doc__,'execution':runtime_metadata(),'source_summary_sha256':sha(origin/'summary.json'),'source_bias_sha256':bias_sha,
        'request':{'fraction':args.fraction,'phase':args.phase,'steps_per_period':args.steps,'periods':args.periods,'settle_early':args.settle_early},
        'nonlinear_assembly':'explicit full gradient/tangent reassembled every iterate' if args.explicit_tangent else 'automatic energy gradient/tangent',
        'newton_linear_solver':'checked current-Jacobian CG / reusable factor preconditioner' if args.reuse_newton_factor else 'fresh sparse Cholesky',
        'residual_evaluation':'state difference before conducting-mass multiplication' if args.stable_residual else 'assembled stepping equation minus history/source',
        'source_resolution':resolution,'material':material,'bias_relative_residual':bias_residual,
        'initial_guess':'exact discrete tangent harmonic orbit, followed by nonlinear equations',
        'source_snapshots':snapshots,'completed_steps':0,'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=time.monotonic()
    raw_previous,raw_mid,raw_next,powers,works,top=[deque(maxlen=2*args.steps) for _ in range(6)]
    max_residual=0.;iterations=0
    probe_x=(np.arange(64)+.37)/64*period;probe_y=(np.arange(16)+.41)/16*thickness
    px,py=np.meshgrid(probe_x,probe_y,indexing='ij');locations=mesh(px.ravel(),py.ravel())
    sampled_min=np.full(px.size,np.inf);sampled_max=np.zeros(px.size)
    factor=None
    if args.reuse_newton_factor:
        from newton_factor import NewtonFactor
        factor=NewtonFactor(ng)
    try:
        for step in range(args.periods*args.steps):
            time_mid=(step+.5)*dt;drive=amplitude*math.sin(omega*time_mid)
            rhs.data=(2/dt)*(mass.mat*previous.vec)+drive*forcing.vec
            def step_residual(vector,result):
                if args.stable_residual:
                    from midpoint_residual import evaluate
                    evaluate(static,mass.mat,vector,previous.vec,forcing.vec,drive,dt,result)
                else:stepping.Apply(vector,result);result.data-=rhs
            midpoint.vec.data=previous.vec
            for iteration in range(40):
                step_residual(midpoint.vec,residual)
                norm=float(np.linalg.norm(residual.FV().NumPy()[free]));relative=norm/reference
                if relative<=1e-10:break
                stepping.AssembleLinearization(midpoint.vec)
                direction.data=factor.solve(stepping.mat,residual,fes.FreeDofs()) if factor else stepping.mat.Inverse(fes.FreeDofs(),inverse='sparsecholesky')*residual
                scale=1.
                for _ in range(30):
                    candidate.vec.data=midpoint.vec-scale*direction
                    trial_residual=residual.CreateVector();step_residual(candidate.vec,trial_residual)
                    if np.linalg.norm(trial_residual.FV().NumPy()[free])<norm:midpoint.vec.data=candidate.vec;break
                    scale*=.5
                else:
                    failed=work/f'failed-step-{step:05d}.npz'
                    with failed.open('xb') as stream:np.savez_compressed(stream,previous=np.array(previous.vec.FV().NumPy()),midpoint=np.array(midpoint.vec.FV().NumPy()),candidate=np.array(candidate.vec.FV().NumPy()),dt=dt,drive=drive,step=step)
                    linear=residual.CreateVector();linear.data=stepping.mat*direction-residual
                    report['line_search_failure']={'step':step,'iteration':iteration,'relative_residual':relative,'last_trial_residual_norm':float(np.linalg.norm(trial_residual.FV().NumPy()[free])),
                        'relative_linear_residual':float(np.linalg.norm(linear.FV().NumPy()[free]))/max(norm,1e-300),'archive':failed.name,'sha256':sha(failed)};save()
                    raise ValueError('Independent FE transient line search failed')
            else:raise ValueError('Independent FE transient Newton step failed')
            max_residual=max(max_residual,relative);iterations+=iteration+1
            next_vector.data=2*midpoint.vec-previous.vec
            old=np.array(previous.vec.FV().NumPy());centre=np.array(midpoint.vec.FV().NumPy());new=np.array(next_vector.FV().NumPy())
            derivative=(new-old)/dt
            powers.append(float(derivative@(mmat@derivative))/period)
            works.append(float(drive*np.dot(forcing.vec.FV().NumPy(),derivative))/period)
            raw_previous.append(old);raw_mid.append(centre);raw_next.append(new)
            top.append(float(ng.Integrate((midpoint-equilibrium)*shape,mesh,definedon=mesh.Boundaries('source'),order=8))*2/period)
            if step%args.steps==0:sampled_min.fill(np.inf);sampled_max.fill(0.)
            total_x=bx+ng.grad(midpoint)[1];total_z=bz+ng.grad(midpoint)[0]
            magnitude=np.hypot(np.asarray(total_x(locations)).reshape(-1),np.asarray(total_z(locations)).reshape(-1))
            if magnitude.shape!=sampled_min.shape:raise ValueError('Wrong scalar probe shape for knee diagnostics')
            sampled_min=np.minimum(sampled_min,magnitude);sampled_max=np.maximum(sampled_max,magnitude)
            previous.vec.data=next_vector
            if (step+1)%args.steps==0:
                count=(step+1)//args.steps;checkpoint=work/f'checkpoint-period-{count}.npz'
                with checkpoint.open('xb') as stream:
                    np.savez_compressed(stream,vector=np.array(previous.vec.FV().NumPy()),source_summary_sha256=report['source_summary_sha256'],
                        mesh_sha256=source['mesh_sha256'],fraction=args.fraction,phase=args.phase,steps_per_period=args.steps,
                        completed_periods=count,version=ng.__version__)
                report.update(completed_steps=step+1,max_step_relative_residual=max_residual,
                    latest_checkpoint=checkpoint.name,latest_checkpoint_sha256=sha(checkpoint))
                if count>=2:
                    recent=np.array(list(raw_mid))-np.array(equilibrium.vec.FV().NumPy())
                    report['last_two_period_relative_change']=float(np.linalg.norm(recent[args.steps:]-recent[:args.steps])/np.linalg.norm(recent[args.steps:]))
                save();print('period',count,'complete',flush=True)
                if args.settle_early and count>=4 and report['last_two_period_relative_change']<=1e-5:break
        raw_mid=np.array(list(raw_mid));ripple=raw_mid-np.array(equilibrium.vec.FV().NumPy())
        settled=float(np.linalg.norm(ripple[args.steps:]-ripple[:args.steps])/np.linalg.norm(ripple[args.steps:]))
        loss=float(np.mean(list(powers)[-args.steps:])/amplitude**2);source_work=float(np.mean(list(works)[-args.steps:])/amplitude**2)
        times=(np.arange(args.steps)+.5)*dt;phasor=2*np.mean(np.array(list(top)[-args.steps:])*np.exp(-1j*omega*times))
        reflection=k[0]*phasor/(-1j*amplitude)-1;balance=abs(source_work/loss-1)
        with (work/'last-two-periods.npz').open('xb') as stream:
            np.savez_compressed(stream,previous=list(raw_previous),midpoints=raw_mid,next=list(raw_next),equilibrium=np.array(equilibrium.vec.FV().NumPy()),
                loss=list(powers),source_work=list(works),top=list(top),dt=dt,amplitude=amplitude,phase=args.phase)
        expected=complex(*source['ac'][args.phase]['reflection']);knee=bsat*mu/(mu-1)
        report.update(periodic_settlement_relative_change=settled,relative_source_work_joule_balance=balance,
            joule_coefficient_w_m2_t2=loss,source_work_coefficient_w_m2_t2=source_work,reflection=[reflection.real,reflection.imag],
            linearized_reflection=[expected.real,expected.imag],linearized_loss_relative_error=abs(loss/source['ac'][args.phase]['joule_coefficient_w_m2_t2']-1),
            sampled_knee_crossing_fraction=float(np.mean((sampled_min<=knee)&(sampled_max>knee))),sampled_peak_b_t=float(sampled_max.max()),
            seconds=time.monotonic()-started,actual_completed_periods=report['completed_steps']//args.steps,
            mean_newton_iterations_per_step=iterations/report['completed_steps'],trace_sha256=sha(work/'last-two-periods.npz'))
        if factor:report['newton_linear_solve_statistics']=factor.stats
        save()
        if not np.isfinite([settled,balance,loss,reflection.real,reflection.imag]).all() or settled>1e-5 or balance>.02 or loss<=0:
            raise ValueError('Independent FE transient settlement or power gate failed')
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('FE transient implementation changed')
        if sha(origin/'summary.json')!=report['source_summary_sha256'] or sha(origin/'bias.sol')!=bias_sha:
            raise ValueError('Independent bias changed during transient')
        report['status']='completed-independent-periodic-nonlinear-transient-unqualified';save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
