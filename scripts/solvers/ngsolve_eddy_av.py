#!/usr/bin/env python3
"""Independent coupled 3D reaction-A / charge-potential eddy benchmark.

The prescribed uniform harmonic B has analytic source E=-i*omega*A_source.
Reaction A, induced magnetic feedback and electric-potential current closure
are solved together. A Coulomb multiplier or an exact checked tree fixes A gauge;
an independent mean-zero multiplier fixes the isolated electric-potential gauge.
No penalty mass, failed-field subtraction or fitted inductance is used.
Disk/sphere benchmarks are not PM motor, nonlinear backplane or motion results.
"""
import argparse
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from post_project_force import sha
from source_snapshot import capture
from solver_threads import add_thread_option,runtime_metadata,threaded_main

MU0=4e-7*math.pi


def weak_disk_loss(radius,thickness,sigma,frequency,peak_b):
    return math.pi*sigma*(2*math.pi*frequency)**2*peak_b**2*thickness*radius**4/16


def disk_mesh(ng,radius,thickness,slot,near,far,air_mesh,shape='disk'):
    from netgen.occ import Sphere,Cylinder,Box,Pnt,Dir,OCCGeometry,Glue
    body=Sphere(Pnt(0,0,0),radius) if shape=='sphere' else Cylinder(Pnt(0,0,-thickness),Dir(0,0,1),radius,thickness)
    if slot:
        cut=Box(Pnt(0,-slot/2,-2*thickness),Pnt(2*radius,slot/2,thickness))
        body=body-cut
    body.mat('conductor');body.maxh=near;body.faces.name='interface';body.faces.maxh=near
    sphere=Sphere(Pnt(0,0,0),far);sphere.faces.name='outer'
    air=sphere-body;air.mat('air');air.maxh=air_mesh
    mesh=ng.Mesh(OCCGeometry(Glue([air,body])).GenerateMesh(maxh=air_mesh))
    mesh.Curve(2)
    return mesh


def av_spaces(ng,mesh,order=0,harmonic=False,gauge='coulomb'):
    a=ng.HCurl(mesh,order=order,dirichlet='outer',complex=harmonic,nograds=gauge=='tree')
    # P2 electric potential contains physical affine coordinates on the P2
    # curved geometry, so the isolated conductor's integrated current moments
    # are tested exactly. The Coulomb space matches A's H1(order+1) gradient kernel.
    potential=ng.Compress(ng.H1(mesh,order=max(2,order+1),definedon=mesh.Materials('conductor'),complex=harmonic))
    if gauge=='tree':return a*potential*ng.NumberSpace(mesh,complex=harmonic)
    multiplier=ng.H1(mesh,order=order+1,dirichlet='outer',complex=harmonic)
    return a*potential*multiplier*ng.NumberSpace(mesh,complex=harmonic)


def solve(ng,mesh,frequency,sigma,peak_b,bonus_order,order=0,gauge='coulomb'):
    fes=av_spaces(ng,mesh,order,harmonic=True,gauge=gauge)
    if gauge=='tree':
        a,p,eta=fes.TrialFunction();v,q,zeta=fes.TestFunction()
        from tree_gauge import free_dofs
        selected,tree_count=free_dofs(ng,mesh,fes,fes.components[0])
    else:
        a,p,lam,eta=fes.TrialFunction();v,q,mu,zeta=fes.TestFunction()
        selected=fes.FreeDofs();tree_count=0
    conductor=mesh.Materials('conductor')
    # Use the same explicit rule in both gauges. Automatic compound-space
    # orders differ in air when the global Coulomb multiplier is removed.
    rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,2*(order+1)+bonus_order)}
    dx=ng.dx(intrules=rules);dc=ng.dx(definedon=conductor,intrules=rules)
    volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,definedon=conductor,order=6))
    omega=2*math.pi*frequency
    length=float(np.max(np.ptp(np.array([vertex.point for vertex in mesh.vertices]),axis=0)))
    # Nondimensional scaling of EXACT zero constraints, not penalty terms.
    # Unscaled multiplier blocks mix metre-sized basis units across many orders
    # of magnitude and can hide gauge invariance in floating-point roundoff.
    coulomb_scale=1/(MU0*length**2)
    mean_scale=sigma*abs(omega)*volume**(1/3)
    form=ng.BilinearForm(fes,symmetric=True)
    form+=(ng.InnerProduct(ng.curl(a),ng.curl(v))/MU0)*dx
    form+=(1j*omega*sigma*ng.InnerProduct(a+ng.grad(p),v+ng.grad(q)))*dc
    if gauge=='coulomb':form+=(coulomb_scale*(ng.InnerProduct(ng.grad(lam),v)+ng.InnerProduct(a,ng.grad(mu))))*dx
    form+=(mean_scale*(p*zeta+q*eta)/volume)*dc
    source_e=ng.CoefficientFunction((1j*omega*peak_b*ng.y/2,-1j*omega*peak_b*ng.x/2,0.))
    rhs=ng.LinearForm(fes);rhs+=(sigma*ng.InnerProduct(source_e,v+ng.grad(q)))*dc
    form.Assemble();rhs.Assemble();solution=ng.GridFunction(fes)
    started=time.monotonic()
    inverse=form.mat.Inverse(selected,inverse='umfpack');solution.vec.data=inverse*rhs.vec
    free=np.array(selected,dtype=bool)
    for _ in range(2):
        old_residual=rhs.vec.CreateVector();old_residual.data=form.mat*solution.vec-rhs.vec
        candidate=solution.vec.CreateVector();candidate.data=solution.vec-inverse*old_residual
        new_residual=rhs.vec.CreateVector();new_residual.data=form.mat*candidate-rhs.vec
        if np.linalg.norm(new_residual.FV().NumPy()[free])>=np.linalg.norm(old_residual.FV().NumPy()[free]):break
        solution.vec.data=candidate
    elapsed=time.monotonic()-started
    residual=rhs.vec.CreateVector();residual.data=form.mat*solution.vec-rhs.vec
    scale=float(np.linalg.norm(rhs.vec.FV().NumPy()[free]))
    relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/scale if scale else float(np.linalg.norm(residual.FV().NumPy()[free]))
    reaction,potential=solution.components[:2]
    current=sigma*(source_e-1j*omega*(reaction+ng.grad(potential)))
    loss=float(ng.Integrate(.5*ng.Norm(current)**2/sigma,mesh,definedon=conductor,order=6))
    source_work=.5*float(ng.Integrate(ng.InnerProduct(current,source_e),mesh,definedon=conductor,order=6).real)
    net=[complex(ng.Integrate(current[i],mesh,definedon=conductor,order=6)) for i in range(3)]
    current_scale=math.sqrt(max(loss*2*sigma*volume,1e-60))
    net_relative=float(np.linalg.norm(net))/current_scale
    balance=abs(source_work/loss-1) if loss>0 else 0. if source_work==0 else float('inf')
    return solution,{'dofs':fes.ndof,'free_dofs':int(free.sum()),'tree_fixed_edges':tree_count,'solve_seconds':elapsed,'relative_equation_residual':relative,
        'conductor_volume_m3':volume,'joule_power_w':loss,'source_work_w':source_work,
        'relative_source_work_joule_balance':balance,'net_volume_current_relative_error':net_relative,
        'reaction_magnetic_energy_time_average_j':float(ng.Integrate(.25*ng.Norm(ng.curl(reaction))**2/MU0,mesh,order=6))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--mesh',type=float,default=.0012)
    parser.add_argument('--far',type=float,default=.03);parser.add_argument('--air-mesh',type=float,default=.0075)
    parser.add_argument('--slot',type=float,default=0.);parser.add_argument('--frequency',type=float,default=1.)
    parser.add_argument('--sigma',type=float,default=25e6);parser.add_argument('--peak-b',type=float,default=.01)
    parser.add_argument('--bonus-order',type=int,default=4)
    parser.add_argument('--shape',choices=['disk','sphere'],default='disk')
    parser.add_argument('--radius',type=float,default=.006);parser.add_argument('--thickness',type=float,default=.001)
    parser.add_argument('--order',type=int,choices=[0,1,2],default=0)
    parser.add_argument('--gauge',choices=['coulomb','tree'],default='coulomb')
    add_thread_option(parser)
    args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous coupled A-v trials')
    if not np.isfinite([args.mesh,args.far,args.air_mesh,args.slot,args.frequency,args.sigma,args.peak_b,args.radius,args.thickness]).all() or min(args.mesh,args.far,args.air_mesh,args.frequency,args.sigma,args.peak_b,args.radius,args.thickness)<=0 or not 0<=args.slot<args.radius or args.far<=2*args.radius or not 0<=args.bonus_order<=12 or (args.shape=='sphere' and args.slot):
        parser.error('Positive finite physical/mesh inputs and slot<radius required')
    import ngsolve as ng
    work.mkdir(parents=True);snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in ['eddy_sphere_reference.py','tree_gauge.py','solver_threads.py']]])
    report={'status':'running','scope':__doc__,'version':ng.__version__,
        'request':{k:v for k,v in vars(args).items() if k not in ['work','threads']},'execution':runtime_metadata(),
        'radius_m':args.radius,'thickness_m':args.thickness if args.shape=='disk' else None,
        'space_orders':{'reaction_hcurl':args.order,'electric_h1':max(2,args.order+1),'coulomb_h1':args.order+1},'source_snapshots':snapshots,'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=time.monotonic()
    try:
        mesh=disk_mesh(ng,args.radius,args.thickness,args.slot,args.mesh,args.far,args.air_mesh,args.shape)
        mesh.ngmesh.Save(str(work/'mesh.vol'))
        solution,proof=solve(ng,mesh,args.frequency,args.sigma,args.peak_b,args.bonus_order,args.order,args.gauge)
        report['proof']=proof;save()
        if not np.isfinite(list(proof.values())).all() or proof['relative_equation_residual']>1e-9 or proof['relative_source_work_joule_balance']>.02 or proof['net_volume_current_relative_error']>1e-9:
            raise ValueError('Coupled A-v equation, power or isolated-current gate failed')
        if args.shape=='sphere':
            from eddy_sphere_reference import dipole_loss,volume_loss,weak_loss
            physical=(args.radius,args.sigma,args.frequency,args.peak_b)
            exact=dipole_loss(*physical);independent=volume_loss(*physical)
            report['sphere_reference']={'dipole_loss_w':exact,'volume_loss_w':independent,
                'weak_limit_loss_w':weak_loss(*physical),'fe_relative_error':abs(proof['joule_power_w']/exact-1)}
            if abs(independent/exact-1)>1e-9:raise ValueError('Independent sphere dipole/volume references disagree')
            if report['sphere_reference']['fe_relative_error']>.05:raise ValueError('Coupled sphere/analytical loss agreement exceeds 5%')
        elif args.slot==0:
            exact=weak_disk_loss(args.radius,args.thickness,args.sigma,args.frequency,args.peak_b)
            report['weak_disk_analytic_loss_w']=exact;report['weak_disk_relative_error']=abs(proof['joule_power_w']/exact-1)
            # This analytic gate is valid only in the weak-diffusion limit.
            induction=MU0*args.sigma*(2*math.pi*args.frequency)*args.radius**2
            report['induction_parameter']=induction
            if induction<=.01 and report['weak_disk_relative_error']>.05:raise ValueError('Analytical weak-disk loss agreement exceeds 5%')
        solution.Save(str(work/'response.sol'))
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Coupled A-v implementation changed during solve')
        report.update(status=f'completed-coupled-3d-av-{args.shape}-unqualified',seconds=time.monotonic()-started,
            mesh_sha256=sha(work/'mesh.vol'),solution_sha256=sha(work/'response.sol'))
        save();print(proof,flush=True)
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
