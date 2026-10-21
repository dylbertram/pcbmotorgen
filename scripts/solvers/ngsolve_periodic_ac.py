#!/usr/bin/env python3
"""Independent 2D FE DC-bias/tensor-AC check of the periodic spectral model.

Quadratic triangular FE, periodic sides and explicit remote air. A prescribed
Fourier PM particular field drives nonlinear reaction A in the magnetic plate.
The AC solve uses the full spatial differential reluctivity tensor evaluated
from that DC bias, plus finite Al wall conductivity. PMs are DC, not AC sources.
Unit incident AC B is a Green-response normalization, not a physical 1T ripple.
No measured material law, finite ends/current closure, motion or PWM claim.
"""
import argparse
import itertools
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


def symmetric_triangle_rule(ng,order):
    """Close the triangle rule under all barycentric permutations.

    A nonsymmetric integration rule acting on the nonsmooth differential law
    can create phase coupling even on a reflection-symmetric mesh. Averaging
    its six coordinate permutations preserves its degree and total weight.
    """
    points=[];weights=[]
    for point in ng.IntegrationRule(ng.ET.TRIG,order):
        x,y=point.point[:2]
        for bary in itertools.permutations((1-x-y,x,y)):
            points.append((bary[1],bary[2]));weights.append(point.weight/6)
    return ng.IntegrationRule(points=points,weights=weights)


def structured_mesh(ng,nx,thickness,cells,wall_cells,gap_cells,far,air_cells):
    from netgen.meshing import Mesh,MeshPoint,Pnt,Element2D,Element1D,IdentificationType,FaceDescriptor
    period=.012;gap=.0001;wall=.001
    ys=np.r_[np.linspace(-far,0,air_cells+1),np.linspace(0,thickness,cells+1)[1:],
        np.linspace(thickness,thickness+gap,gap_cells+1)[1:],
        np.linspace(thickness+gap,thickness+gap+wall,wall_cells+1)[1:],
        np.linspace(thickness+gap+wall,thickness+gap+wall+far,air_cells+1)[1:]]
    mesh=Mesh(dim=2)
    for region in range(1,4):mesh.Add(FaceDescriptor(surfnr=region,domin=region,bc=region))
    points=[[mesh.Add(MeshPoint(Pnt(x,y,0))) for x in np.linspace(0,period,nx+1)] for y in ys]
    for j in range(len(ys)-1):
        midpoint=(ys[j]+ys[j+1])/2
        material=2 if 0<midpoint<thickness else 3 if thickness+gap<midpoint<thickness+gap+wall else 1
        for i in range(nx):
            a,b=points[j][i:i+2];d,c=points[j+1][i:i+2]
            # Reflect diagonals across x=period/2. A uniform diagonal pattern
            # breaks the source parity and creates numerical phase coupling.
            if i<nx//2:
                mesh.Add(Element2D(material,[a,b,c]));mesh.Add(Element2D(material,[a,c,d]))
            else:
                mesh.Add(Element2D(material,[a,b,d]));mesh.Add(Element2D(material,[b,c,d]))
    for i in range(nx):
        mesh.Add(Element1D([points[0][i],points[0][i+1]],index=1))
        mesh.Add(Element1D([points[-1][i+1],points[-1][i]],index=2))
    for j in range(len(ys)-1):
        mesh.Add(Element1D([points[j+1][0],points[j][0]],index=3))
        mesh.Add(Element1D([points[j][-1],points[j+1][-1]],index=4))
    source=int(np.flatnonzero(ys==0)[0])
    for i in range(nx):mesh.Add(Element1D([points[source][i],points[source][i+1]],index=5))
    for row in points:mesh.AddPointIdentification(row[0],row[-1],identnr=1,type=IdentificationType.PERIODIC)
    for i,name in enumerate(['far_top','far_bottom','left','right','source']):mesh.SetBCName(i,name)
    for i,name in enumerate(['air','plate','wall'],1):mesh.SetMaterial(i,name)
    return ng.Mesh(mesh)


def source_modes(modes):
    # Integrate the actual periodic rectangular magnet surface charge, not
    # a fitted fundamental: width 5mm, pole pitch 6mm, height 3mm, Br=1.34T.
    n=np.arange(1,2*modes,2);k=n*math.pi/.006
    incident=2*1.34/(math.pi*n)*np.sin(n*math.pi*.005/(2*.006))*np.exp(-k*.0013)*(1-np.exp(-k*.003))
    return k,incident


def energy(ng,bx,bz,mu,bsat):
    squared=bx*bx+bz*bz;knee=bsat*mu/(mu-1)
    radius=ng.sqrt(ng.IfPos(squared,squared,1.))
    constant=knee*knee/(2*MU0*mu)-(knee-bsat)**2/(2*MU0)
    return ng.IfPos(squared-knee*knee,(radius-bsat)**2/(2*MU0)+constant,squared/(2*MU0*mu))


def tensor(ng,bx,bz,mu,bsat):
    squared=bx*bx+bz*bz;knee=bsat*mu/(mu-1)
    radius=ng.sqrt(ng.IfPos(squared,squared,1.))
    nu=ng.IfPos(squared-knee*knee,(1-bsat/radius)/MU0,1/(MU0*mu))
    extra=ng.IfPos(squared-knee*knee,bsat/(MU0*radius**3),0.)
    return nu+extra*bx*bx,extra*bx*bz,nu+extra*bz*bz


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--case',choices=['flex_0.2','mnzn_2'],default='mnzn_2')
    parser.add_argument('--nx',type=int,default=96);parser.add_argument('--cells',type=int,default=24)
    parser.add_argument('--wall-cells',type=int,default=32);parser.add_argument('--gap-cells',type=int,default=4)
    parser.add_argument('--air-cells',type=int,default=32);parser.add_argument('--far',type=float,default=.02)
    parser.add_argument('--source-modes',type=int,default=9);parser.add_argument('--bonus-order',type=int,default=4)
    parser.add_argument('--frequency',type=float,default=100000.)
    parser.add_argument('--initial-work',type=Path,help='completed same-material FE bias as an initial guess only')
    add_thread_option(parser)
    args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous tensor-AC trials')
    if min(args.nx,args.cells,args.wall_cells,args.gap_cells,args.air_cells,args.source_modes)<2 or args.nx%2 or not 0<=args.bonus_order<=12 or not np.isfinite([args.far,args.frequency]).all() or args.far<=0 or args.frequency<=0:
        parser.error('Positive resolutions, frequency and air extent required')
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    thickness,mu,bsat,sigma_layer={'flex_0.2':(.0002,130.,.25,0.),'mnzn_2':(.002,2500.,.45,.2)}[args.case]
    work.mkdir(parents=True);snapshots=capture(work,[Path(__file__),Path(__file__).with_name('solver_threads.py')])
    report={'status':'running','scope':__doc__,'case':args.case,'version':ng.__version__,
        'material':{'thickness_m':thickness,'mu_initial':mu,'saturation_polarization_t':bsat,'conductivity_s_m':sigma_layer},
        'resolution':{k:v for k,v in vars(args).items() if k not in ['work','case','initial_work','threads']},'execution':runtime_metadata(),
        'mirror_symmetric_triangulation':True,'source_snapshots':snapshots,'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=time.monotonic()
    try:
        mesh=structured_mesh(ng,args.nx,thickness,args.cells,args.wall_cells,args.gap_cells,args.far,args.air_cells)
        mesh.ngmesh.Save(str(work/'mesh.vol'))
        fes=ng.Periodic(ng.H1(mesh,order=2,dirichlet='far_top|far_bottom'))
        reaction=ng.GridFunction(fes);trial=fes.TrialFunction()
        k,amplitude=source_modes(args.source_modes)
        bx=ng.CoefficientFunction(0.);bz=ng.CoefficientFunction(0.)
        for wave,incident in zip(k,amplitude):
            bx+=-incident*ng.sin(wave*ng.x)*ng.exp(-wave*ng.y)
            bz+=incident*ng.cos(wave*ng.x)*ng.exp(-wave*ng.y)
        bx=ng.CacheCF(bx.Compile());bz=ng.CacheCF(bz.Compile())
        dx=ng.grad(trial)[1];dz=ng.grad(trial)[0]
        form=ng.BilinearForm(fes,symmetric=True)
        rule=symmetric_triangle_rule(ng,4+args.bonus_order)
        measure=lambda region:ng.dx(definedon=mesh.Materials(region),intrules={ng.ET.TRIG:rule})
        density=(energy(ng,bx+dx,bz+dz,mu,bsat)-(bx*dx+bz*dz)/MU0).Compile()
        form+=ng.Variation(density*measure('plate'))
        form+=ng.Variation((ng.InnerProduct(ng.grad(trial),ng.grad(trial))/(2*MU0))*measure('air|wall'))
        residual=reaction.vec.CreateVector();free=np.array(fes.FreeDofs(),dtype=bool)
        form.Apply(reaction.vec,residual);reference=float(np.linalg.norm(residual.FV().NumPy()[free]))
        if args.initial_work:
            from compare_reduced_fields import completed_receipt
            old_work=args.initial_work.resolve();old=json.loads((old_work/'summary.json').read_text());completed_receipt(old)
            if old['status']!='completed-periodic-tensor-ac-unqualified' or old['case']!=args.case or old['material']!=report['material'] or old['version']!=ng.__version__:
                raise ValueError('Need a completed same-material periodic bias for initialization')
            if sha(old_work/'mesh.vol')!=old['mesh_sha256']:raise ValueError('Initial-guess mesh changed')
            old_mesh=ng.Mesh(str(old_work/'mesh.vol'))
            old_fes=ng.Periodic(ng.H1(old_mesh,order=2,dirichlet='far_top|far_bottom'))
            old_bias=ng.GridFunction(old_fes);old_bias.Load(str(old_work/'bias.sol'))
            far=old['resolution']['far'];bottom=thickness+.0001+.001
            lower=-.9*far;upper=bottom+.9*far
            taper=ng.IfPos(ng.y+.8*far,1.,(ng.y-lower)/(.1*far))*ng.IfPos(bottom+.8*far-ng.y,1.,(upper-ng.y)/(.1*far))
            reaction.Set(ng.IfPos(ng.y-lower,ng.IfPos(upper-ng.y,old_bias*taper,0.),0.))
            if not np.isfinite(reaction.vec.FV().NumPy()).all():raise ValueError('Nonfinite periodic initial guess')
            report['initial_guess']={'summary_sha256':sha(old_work/'summary.json'),'bias_sha256':sha(old_work/'bias.sol'),
                'work':str(old_work),'scope':'Initial guess only; taper strictly within old exterior; new equations must reconverge'}
            save()
        result=NewtonMinimization(form,reaction,maxit=80,maxerr=1e-12,inverse='sparsecholesky',linesearch=True,printing=True)
        form.Apply(reaction.vec,residual);relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/reference
        report['bias']={'newton_result':list(result),'relative_equation_residual':relative,'dofs':fes.ndof}
        save()
        if result[0]!=0 or not np.isfinite(relative) or relative>1e-9:raise ValueError('Independent periodic bias did not converge')
        reaction.Save(str(work/'bias.sol'))
        report['bias_solution_sha256']=sha(work/'bias.sol')
        total_bx=bx+ng.grad(reaction)[1];total_bz=bz+ng.grad(reaction)[0]
        dxx,dxz,dzz=tensor(ng,total_bx,total_bz,mu,bsat)
        complex_fes=ng.Periodic(ng.H1(mesh,order=2,complex=True,dirichlet='far_top|far_bottom'))
        a,v=complex_fes.TnT();ax,az=ng.grad(a)[1],ng.grad(a)[0];vx,vz=ng.grad(v)[1],ng.grad(v)[0]
        ac=ng.BilinearForm(complex_fes,symmetric=True);omega=2*math.pi*args.frequency
        ac+=(dxx*ax*vx+dxz*(ax*vz+az*vx)+dzz*az*vz+1j*omega*sigma_layer*a*v)*measure('plate')
        ac+=(ng.InnerProduct(ng.grad(a),ng.grad(v))/MU0)*measure('air|wall')
        ac+=(1j*omega*25e6*a*v)*measure('wall')
        ac.Assemble();inverse=ac.mat.Inverse(complex_fes.FreeDofs(),inverse='umfpack')
        report['ac']=[]
        for phase,source in enumerate([ng.sin(k[0]*ng.x),ng.cos(k[0]*ng.x)]):
            rhs=ng.LinearForm(complex_fes);rhs+=(2/MU0*source*v)*ng.ds('source',bonus_intorder=args.bonus_order);rhs.Assemble()
            response=ng.GridFunction(complex_fes);response.vec.data=inverse*rhs.vec
            error=rhs.vec.CreateVector();error.data=ac.mat*response.vec-rhs.vec
            selected=np.array(complex_fes.FreeDofs(),dtype=bool)
            relative=float(np.linalg.norm(error.FV().NumPy()[selected])/np.linalg.norm(rhs.vec.FV().NumPy()[selected]))
            top=complex(ng.Integrate(response*source,mesh,definedon=mesh.Boundaries('source'),order=8))*2/.012
            reflection=k[0]*top-1
            other=ng.cos(k[0]*ng.x) if phase==0 else ng.sin(k[0]*ng.x)
            cross=complex(ng.Integrate(response*other,mesh,definedon=mesh.Boundaries('source'),order=8))*2*k[0]/.012
            loss=float(ng.Integrate(.5*sigma_layer*omega**2*ng.Norm(response)**2,mesh,definedon=mesh.Materials('plate'),order=8)+
                ng.Integrate(.5*25e6*omega**2*ng.Norm(response)**2,mesh,definedon=mesh.Materials('wall'),order=8))/.012
            work_done=-omega*reflection.imag/(2*MU0*k[0])
            report['last_phase_diagnostic']={'phase':phase,'reflection':[reflection.real,reflection.imag],
                'cross_phase_reflection':[cross.real,cross.imag],'relative_equation_residual':relative,
                'joule_coefficient_w_m2_t2':loss,'source_work_coefficient_w_m2_t2':work_done}
            save()
            if not np.isfinite([relative,loss,work_done,reflection.real,reflection.imag,cross.real,cross.imag]).all() or relative>1e-9 or loss<=0 or abs(work_done/loss-1)>.02:
                raise ValueError('AC equation or source-work/Joule balance failed')
            if abs(cross)>1e-8:raise ValueError('Unexpected cross-phase response for the symmetric bias')
            report['ac'].append({'reflection':[reflection.real,reflection.imag],'joule_coefficient_w_m2_t2':loss,
                'source_work_coefficient_w_m2_t2':work_done,'relative_equation_residual':relative,'cross_phase_reflection':[cross.real,cross.imag]})
            response.Save(str(work/f'ac-{phase}.sol'));save()
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Periodic FE implementation changed during solve')
        if args.initial_work and (sha(args.initial_work/'summary.json')!=report['initial_guess']['summary_sha256'] or sha(args.initial_work/'bias.sol')!=report['initial_guess']['bias_sha256']):
            raise ValueError('Initial-guess source changed during periodic solve')
        report.update(status='completed-periodic-tensor-ac-unqualified',seconds=time.monotonic()-started,mesh_sha256=sha(work/'mesh.vol'))
        save()
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
