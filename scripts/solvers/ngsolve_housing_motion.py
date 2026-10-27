#!/usr/bin/env python3
"""Finite nonmagnetic housing with translating analytical PMs, coupled 3D A-v.

The housing is stationary; E_source=-v_PM cross B_PM satisfies Faraday's law
for rigidly translated prescribed PMs. Reaction A and charge potential are
solved together, including induced magnetic feedback. Midpoint stepping checks
source work = Joule heat + change of reaction magnetic energy, not F*v=P at
array entry/exit. Reported forces are on housing currents. Mover force still
needs independent extraction; it is not obtained by negating a failed floor.
The original ferrite and winding are explicitly EXCLUDED in this baseline.
"""
import argparse
import json
import math
import os
import shutil
from pathlib import Path
import time

import numpy as np

from ngsolve_reduced import source_coefficient
from post_project_force import sha
from post_reduced_force import case_field
from reduced_inputs import validate_reduced_inputs
from reduced_potential import source_field,MU0
from solver_threads import add_thread_option,runtime_metadata,threaded_main
from source_snapshot import capture
from tree_gauge import free_dofs
from compare_reduced_fields import completed_receipt


def moving_source(ng,model,offset):
    # Build new origins without mutating the archived physical model.
    moving={'magnets':[dict(m,origin_m=[m['origin_m'][0]+offset,*m['origin_m'][1:]]) for m in model['magnets']]}
    return source_coefficient(ng,moving).Compile()


def source_electric(ng,field,speed):
    return ng.CoefficientFunction((0.,speed*field[2],-speed*field[1]))


def cross(ng,a,b):
    return ng.CoefficientFunction((a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]))


def profile(speed,span,steps,start=None):
    if not np.isfinite([speed,span]).all() or span<=0 or steps<2:raise ValueError('Invalid motion profile')
    duration=span/abs(speed) if speed else .001
    initial=(-math.copysign(span/2,speed) if speed else 0.) if start is None else start
    if not np.isfinite(initial):raise ValueError('Nonfinite initial source position')
    return initial,duration,duration/steps


def housing_mesh(ng,housing,near,far,air_mesh,slot):
    from netgen.occ import Box,Sphere,Pnt,OCCGeometry,Glue
    low=np.array(housing['origin_m']);high=low+housing['size_m'];centre=(low+high)/2
    if np.max(np.linalg.norm([low,high],axis=1))>=.7*far:raise ValueError('Housing approaches reaction-field exterior')
    body=Box(Pnt(*low),Pnt(*high))
    if slot:
        cut=Box(Pnt(centre[0]-slot/2,centre[1],low[2]-.001),Pnt(centre[0]+slot/2,high[1]+.001,high[2]+.001))
        body=body-cut
    body.mat('conductor');body.maxh=near;body.faces.name='interface';body.faces.maxh=near
    outer=Sphere(Pnt(0,0,0),far);outer.faces.name='outer'
    air=outer-body;air.mat('air');air.maxh=air_mesh
    mesh=ng.Mesh(OCCGeometry(Glue([air,body])).GenerateMesh(maxh=air_mesh));mesh.Curve(2)
    return mesh


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--sigma',type=float,required=True);parser.add_argument('--speed',type=float,default=20.)
    parser.add_argument('--span',type=float,default=.12);parser.add_argument('--start-x',type=float)
    parser.add_argument('--steps',type=int,default=240);parser.add_argument('--mesh',type=float,default=.0015)
    parser.add_argument('--far',type=float,default=.06);parser.add_argument('--air-mesh',type=float,default=.012)
    parser.add_argument('--slot',type=float,default=0.);parser.add_argument('--order',type=int,choices=[0,1,2],default=2)
    parser.add_argument('--bonus-order',type=int,default=4);parser.add_argument('--save-every',type=int,default=40)
    parser.add_argument('--mesh-from',type=Path,help='reuse verified completed housing mesh for time/reverse controls')
    add_thread_option(parser);args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve all previous motion trials')
    if not np.isfinite([args.sigma,args.mesh,args.far,args.air_mesh,args.slot]).all() or min(args.sigma,args.mesh,args.far,args.air_mesh)<=0 or args.slot<0 or not 0<=args.bonus_order<=12 or args.save_every<1:
        parser.error('Invalid conductor, mesh, quadrature or checkpoint settings')
    start,duration,dt=profile(args.speed,args.span,args.steps,args.start_x)
    source=json.loads((origin/'summary.json').read_text());case_field(origin,source,'bare');validate_reduced_inputs(origin,source)
    model=source['model'];houses=[m for m in model['stack'] if m['name']=='housing']
    if len(houses)!=1 or houses[0]['mu_r']!=1:parser.error('Baseline requires one nonmagnetic housing')
    housing=houses[0]
    if args.slot>=min(housing['size_m'][:2]):parser.error('Slot must leave one connected conductor')
    import ngsolve as ng
    work.mkdir(parents=True)
    snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
        ['ngsolve_reduced.py','tree_gauge.py','solver_threads.py','reduced_inputs.py','reduced_potential.py']]])
    report={'status':'running','scope':__doc__,'version':ng.__version__,'execution':runtime_metadata(),
        'request':{k:v for k,v in vars(args).items() if k not in ['source_work','work','threads','mesh_from']},
        'source_summary_sha256':sha(origin/'summary.json'),'model':model,'housing':housing,
        'excluded_materials':[m for m in model['stack'] if m['name']!='housing'],
        'frame':'stationary finite conductor, translating prescribed PM field',
        'initial_state':'zero reaction at rest in the initial static source; prescribed velocity starts at t=0',
        'termination':'integration ends at the final position; no velocity-stop or subsequent decay segment is assumed',
        'potential_variable':'chi=(dt/2)*electric potential; current uses (2/dt)*grad(chi)',
        'profile':{'start_offset_m':start,'end_offset_m':start+args.speed*duration,'duration_s':duration,'dt_s':dt},
        'magnetic_reynolds_number':MU0*args.sigma*abs(args.speed)*max(housing['size_m']),
        'source_snapshots':snapshots,'steps':[],'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=time.monotonic()
    try:
        if args.mesh_from:
            old_work=args.mesh_from.resolve();old=json.loads((old_work/'summary.json').read_text())
            if not old.get('command_receipt'):raise ValueError('Missing completed mesh-source receipt')
            completed_receipt(old)
            if old['status']!='completed-finite-housing-coupled-motion-unqualified' or old['failures'] or old['housing']!=housing:
                raise ValueError('Need a completed same-housing geometry for mesh reuse')
            if any(old['request'][name]!=getattr(args,name) for name in ['mesh','far','air_mesh','slot']):
                raise ValueError('Requested geometry controls differ from the reusable mesh')
            if sha(old_work/'mesh.vol')!=old['mesh_sha256']:raise ValueError('Reusable housing mesh changed')
            shutil.copy2(old_work/'mesh.vol',work/'mesh.vol');mesh=ng.Mesh(str(work/'mesh.vol'))
            report['mesh_reuse']={'source_summary_sha256':sha(old_work/'summary.json'),'mesh_sha256':old['mesh_sha256']}
        else:
            mesh=housing_mesh(ng,housing,args.mesh,args.far,args.air_mesh,args.slot);mesh.ngmesh.Save(str(work/'mesh.vol'))
        a_space=ng.HCurl(mesh,order=args.order,nograds=True,dirichlet='outer')
        p_space=ng.Compress(ng.H1(mesh,order=max(2,args.order+1),definedon=mesh.Materials('conductor')))
        fes=a_space*p_space;a,p=fes.TrialFunction();v,q=fes.TestFunction()
        selected,tree_count=free_dofs(ng,mesh,fes,a_space)
        # One scalar reference fixes only an additive potential constant. It
        # does not impose a terminal voltage/current or connect conductor walls.
        reference=next(d for vertex in mesh.vertices for d in p_space.GetDofNrs(ng.NodeId(ng.VERTEX,vertex.nr)) if d>=0)
        selected[a_space.ndof+reference]=False;free=np.array(selected,dtype=bool)
        integration_order=2*(args.order+1)+args.bonus_order
        rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,integration_order)}
        dx=ng.dx(intrules=rules);dc=ng.dx(definedon=mesh.Materials('conductor'),intrules=rules)
        stiffness=ng.BilinearForm(fes,symmetric=True);stiffness+=(ng.InnerProduct(ng.curl(a),ng.curl(v))/MU0)*dx;stiffness.Assemble()
        beta=2*args.sigma/dt
        form=ng.BilinearForm(fes,symmetric=True)
        form+=(ng.InnerProduct(ng.curl(a),ng.curl(v))/MU0)*dx
        form+=(beta*ng.InnerProduct(a+ng.grad(p),v+ng.grad(q)))*dc;form.Assemble()
        history=ng.BilinearForm(fes);history+=(beta*ng.InnerProduct(a,v+ng.grad(q)))*dc;history.Assemble()
        position=ng.Parameter(start);bsource=moving_source(ng,model,position);esource=source_electric(ng,bsource,args.speed).Compile()
        load=ng.LinearForm(fes);load+=(args.sigma*ng.InnerProduct(esource,v+ng.grad(q)))*dc
        rng=np.random.default_rng(9017);low=np.array(housing['origin_m']);size=np.array(housing['size_m'])
        probes=low+rng.uniform(.13,.87,(32,3))*size;incident=source_field(model);maximum=0.
        for offset in [start,0.,start+args.speed*duration]:
            position.Set(offset)
            sampled=np.asarray(bsource(mesh(probes[:,0],probes[:,1],probes[:,2]))).reshape(-1,3)
            maximum=max(maximum,float(np.max(abs(sampled-incident(probes-np.array([offset,0.,0.]))))))
        report.update(source_coefficient_error_t=maximum,dofs=fes.ndof,free_dofs=int(free.sum()),tree_fixed_edges=tree_count,
            mesh_sha256=sha(work/'mesh.vol'),potential_reference='one scalar vertex; gauge only')
        if maximum>1e-10:raise ValueError('Moving source disagrees with independent cuboid field')
        previous=ng.GridFunction(fes);midpoint=ng.GridFunction(fes);derivative=ng.GridFunction(fes)
        next_vector=previous.vec.CreateVector();rhs=previous.vec.CreateVector()
        factor_started=time.monotonic();inverse=form.mat.Inverse(selected,inverse='sparsecholesky')
        report['factor_seconds']=time.monotonic()-factor_started;save()
        conductor=mesh.Materials('conductor')
        integrate=lambda field:ng.Integrate(field,mesh,definedon=conductor,order=integration_order)
        volume=float(integrate(ng.CoefficientFunction(1.)))
        a_mid,p_mid=midpoint.components
        current=args.sigma*(esource-derivative.components[0]-2/dt*ng.grad(p_mid))
        force_cf=cross(ng,current,bsource);self_cf=cross(ng,current,ng.curl(a_mid))
        # Fuse observables so the moving cuboid field is not recomputed in a
        # dozen separate volume integrations at every time step.
        observables=ng.CoefficientFunction(tuple([ng.InnerProduct(current,current)/args.sigma,ng.InnerProduct(current,esource)]+
            [force_cf[i] for i in range(3)]+[self_cf[i] for i in range(3)]+[current[i] for i in range(3)]+
            [args.sigma*ng.InnerProduct(esource,esource)])).Compile()
        balance_max=0.;equation_max=0.;net_max=0.;source_energy=0.;joule_energy=0.;stored_old=0.;saved=[]
        for step in range(args.steps):
            offset=start+args.speed*(step+.5)*dt;position.Set(offset);load.Assemble()
            rhs.data=history.mat*previous.vec+load.vec;midpoint.vec.data=inverse*rhs
            residual=rhs.CreateVector();residual.data=form.mat*midpoint.vec-rhs
            scale=float(np.linalg.norm(rhs.FV().NumPy()[free]));error=float(np.linalg.norm(residual.FV().NumPy()[free]))/scale if scale else float(ng.Norm(residual))
            equation_max=max(equation_max,error)
            next_vector.FV().NumPy()[:]=0.
            next_vector.FV().NumPy()[:a_space.ndof]=2*midpoint.vec.FV().NumPy()[:a_space.ndof]-previous.vec.FV().NumPy()[:a_space.ndof]
            derivative.vec.data=(1/dt)*(next_vector-previous.vec)
            values=np.asarray(integrate(observables),dtype=float).reshape(-1)
            if values.shape!=(12,):raise ValueError('Wrong moving-field observable dimensions')
            loss,work_done=map(float,values[:2]);force=values[2:5];self_force=values[5:8];net=values[8:11]
            stored_new=.5*float(np.dot(next_vector.FV().NumPy(),(stiffness.mat*next_vector).Evaluate().FV().NumPy()))
            rate=(stored_new-stored_old)/dt
            balance=abs(work_done-loss-rate)/max(abs(work_done),loss,abs(rate),1e-20)
            source_scale=float(values[11])
            net_relative=float(np.linalg.norm(net))/max(math.sqrt(max(loss,source_scale,0.)*args.sigma*volume),1e-30)
            net_max=max(net_max,net_relative);balance_max=max(balance_max,balance)
            if not np.isfinite([error,loss,work_done,stored_new,balance,net_relative,*force,*self_force]).all() or error>1e-9 or balance>.02 or net_relative>1e-9 or loss<0:
                raise ValueError('Motion equation/current/energy gate failed at step '+str(step))
            record={'step':step,'time_mid_s':(step+.5)*dt,'source_offset_m':offset,'joule_power_w':loss,'source_work_w':work_done,
                'reaction_energy_end_j':stored_new,'housing_source_interaction_force_n':force.tolist(),'housing_self_force_n':self_force.tolist(),
                'relative_energy_balance':balance,'relative_equation_residual':error,'net_current_relative_error':net_relative}
            report['steps'].append(record);source_energy+=work_done*dt;joule_energy+=loss*dt
            if (step+1)%args.save_every==0 or step==args.steps//2:
                name=f'midpoint-{step:05d}.sol';midpoint.Save(str(work/name));saved.append({'step':step,'file':name,'sha256':sha(work/name)})
                print('step',step,'offset',offset,'loss',loss,'interaction force',force.tolist(),flush=True)
            previous.vec.data=next_vector;stored_old=stored_new
            if (step+1)%args.save_every==0:
                name=f'checkpoint-{step+1:05d}.sol';previous.Save(str(work/name));report['latest_checkpoint']={'file':name,'sha256':sha(work/name)}
            save()
        force_scale=max(np.linalg.norm(row['housing_source_interaction_force_n']) for row in report['steps'])
        self_max=max(np.linalg.norm(row['housing_self_force_n']) for row in report['steps'])
        self_limit=max(1e-8,.02*force_scale)
        if self_max>self_limit:report['failures'].append('Housing self-force exceeds max(10nN, 2% peak interaction force)')
        report.update(source_work_energy_j=source_energy,joule_energy_j=joule_energy,reaction_energy_end_j=stored_old,
            integrated_energy_balance=abs(source_energy-joule_energy-stored_old)/max(abs(source_energy),joule_energy,stored_old,1e-30),
            maximum_step_energy_balance=balance_max,maximum_relative_equation_residual=equation_max,maximum_net_current_relative_error=net_max,
            maximum_housing_self_force_n=self_max,self_force_limit_n=self_limit,saved_midpoints=saved,
            seconds=time.monotonic()-started,conductor_volume_m3=volume)
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Motion implementation changed during solve')
        if sha(origin/'summary.json')!=report['source_summary_sha256']:raise ValueError('Original physical source changed')
        report['status']='failed' if report['failures'] else 'completed-finite-housing-coupled-motion-unqualified';save()
        if report['failures']:raise ValueError('\n'.join(report['failures']))
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
