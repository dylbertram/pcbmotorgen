#!/usr/bin/env python3
"""Finite isolated housing current closure in the low-magnetic-Reynolds limit.

Solves div J=0 with J=sigma*(-grad V+u cross B) and natural insulating walls
in a finite 3D conductor. B is the analytical five-PM source, not a coupled
induced field or nonlinear backplane response. This is a controlled low-speed
limit, NOT an operating-speed drag prediction. Rm uses the longest housing
dimension; jobs reject Rm>0.01 rather than extrapolate to motor speeds.
"""
import argparse
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from ngsolve_reduced import source_coefficient
from post_project_force import sha
from reduced_potential import MU0,source_field
from source_snapshot import capture


def cross(ng,a,b):
    return ng.CoefficientFunction((a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]))


def rectangle_gradient_loss(size,sigma,speed,gradient=1.):
    """Exact isolated slab loss for B=gradient*(z,0,x), u along x.

    The independent streamfunction solves -laplacian(u)=1, u=0 on the
    rectangular perimeter. Its torsional-rigidity Fourier series gives
    P=sigma*speed^2*gradient^2*thickness*integral(u). This is not a PM-source
    or high-Rm reference. The electric-potential solve uses no such series.
    """
    a,b=sorted(size[:2],reverse=True);thickness=size[2]
    if min(a,b,thickness,sigma)<=0:raise ValueError('Positive slab dimensions and conductivity required')
    series=sum(math.tanh(n*math.pi*a/(2*b))/n**5 for n in range(1,2000,2))
    integral=a*b**3/12*(1-192*b/(math.pi**5*a)*series)
    return sigma*speed**2*gradient**2*thickness*integral


def solve(ng,mesh,field,sigma,speed,bonus=4):
    fes=ng.H1(mesh,order=2)*ng.NumberSpace(mesh)
    potential,multiplier=fes.TrialFunction();test,constant=fes.TestFunction()
    velocity=ng.CoefficientFunction((speed,0.,0.));emf=cross(ng,velocity,field)
    # Divide by sigma for conditioning. The mean-zero constraint fixes only
    # electric-potential gauge and does not inject current or short any wall.
    form=ng.BilinearForm(fes,symmetric=True)
    form+=(ng.InnerProduct(ng.grad(potential),ng.grad(test))+multiplier*test+potential*constant)*ng.dx(bonus_intorder=bonus)
    rhs=ng.LinearForm(fes);rhs+=ng.InnerProduct(emf,ng.grad(test))*ng.dx(bonus_intorder=bonus)
    form.Assemble();rhs.Assemble();solution=ng.GridFunction(fes)
    solution.vec.data=form.mat.Inverse(fes.FreeDofs(),inverse='umfpack')*rhs.vec
    residual=rhs.vec.CreateVector();residual.data=form.mat*solution.vec-rhs.vec
    norm=float(ng.Norm(rhs.vec));relative=float(ng.Norm(residual))/norm if norm else float(ng.Norm(residual))
    current=sigma*(emf-ng.grad(solution.components[0]))
    integrate=lambda value:ng.Integrate(value,mesh,order=2*2+bonus)
    power=float(integrate(ng.InnerProduct(current,current)/sigma))
    force=np.array([float(integrate(cross(ng,current,field)[i])) for i in range(3)])
    net=np.array([float(integrate(current[i])) for i in range(3)])
    volume=float(integrate(ng.CoefficientFunction(1.)))
    source_scale=float(integrate(sigma*ng.InnerProduct(emf,emf)))
    balance=abs(power+force[0]*speed)/max(power,1e-30)
    net_relative=float(np.linalg.norm(net))/max(math.sqrt(max(0.,source_scale*sigma*volume)),1e-30)
    return {'equation_relative_residual':relative,'joule_power_w':power,'housing_force_n':force.tolist(),
        'net_volume_current_a_m':net.tolist(),'volume_m3':volume,'source_power_scale_w':source_scale,
        'mechanical_joule_relative_balance':balance,'net_current_relative_error':net_relative,'dofs':fes.ndof}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--sigma',type=float,required=True);parser.add_argument('--speed',type=float,default=.001)
    parser.add_argument('--meshes',type=float,nargs='+',default=[.003,.002,.0015])
    parser.add_argument('--bonus-order',type=int,default=4)
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous current-closure trials')
    if not 0<=args.bonus_order<=12:parser.error('Integration bonus order must be in [0,12]')
    if not np.isfinite([args.sigma,args.speed,*args.meshes]).all() or args.sigma<=0 or args.speed<=0 or len(args.meshes)<2 or any(v<=0 for v in args.meshes) or any(a<=b for a,b in zip(args.meshes,args.meshes[1:])):
        parser.error('Positive conductivity/speed and decreasing positive mesh sizes required')
    from compare_reduced_fields import field_case
    report,_,_,_=field_case(origin)
    model=report['model'];housing=[m for m in model['stack'] if m['name']=='housing']
    if len(housing)!=1 or housing[0]['mu_r']!=1:parser.error('Need a single nonmagnetic finite housing')
    housing=housing[0];length=max(housing['size_m']);rm=MU0*args.sigma*args.speed*length
    if rm>.01:parser.error('Rm>0.01: a coupled induced-field solve is required')
    import ngsolve as ng
    from netgen.occ import Box,Pnt,OCCGeometry
    low=np.array(housing['origin_m']);high=low+housing['size_m']
    b=source_coefficient(ng,model).Compile();incident=source_field(model)
    work.mkdir(parents=True);snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in ['ngsolve_reduced.py','reduced_potential.py']]])
    output={'status':'running','scope':__doc__,'version':ng.__version__,'source_summary_sha256':sha(origin/'summary.json'),
        'sigma_s_m':args.sigma,'speed_m_s':args.speed,'magnetic_reynolds_number':rm,'housing':housing,'bonus_order':args.bonus_order,
        'slot':'0.5mm-wide central x slit from y=0 to +y edge, through thickness; remaining conductor connected',
        'source_snapshots':snapshots,'levels':{},'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save();start=time.monotonic()
    try:
        for h in args.meshes:
            level={}
            for name in ['closed','slotted']:
                solid=Box(Pnt(*low),Pnt(*high))
                if name=='slotted':
                    centre=(low+high)/2
                    slot=Box(Pnt(centre[0]-.00025,centre[1],low[2]-.001),Pnt(centre[0]+.00025,high[1]+.001,high[2]+.001))
                    solid=solid-slot
                mesh=ng.Mesh(OCCGeometry(solid).GenerateMesh(maxh=h))
                mesh.ngmesh.Save(str(work/f'{name}-{h:.6f}.vol'))
                # Cross-check analytical coefficient at interior physical points.
                points=np.array([low+.21*(high-low),low+.73*(high-low)])
                sampled=np.array(b(mesh(points[:,0],points[:,1],points[:,2]))).reshape(-1,3)
                if np.max(abs(sampled-incident(points)))>1e-10:raise ValueError('Source coefficient differs from analytical field')
                runs={}
                for label,speed,field in [('zero',0.,b),('forward',args.speed,b),('reverse',-args.speed,b),
                    ('uniform',args.speed,ng.CoefficientFunction((0.,0.,.2))),
                    ('gradient',args.speed,ng.CoefficientFunction((ng.z-(low[2]+high[2])/2,0.,ng.x-(low[0]+high[0])/2)))]:
                    result=solve(ng,mesh,field,args.sigma,speed,args.bonus_order);runs[label]=result
                    if result['equation_relative_residual']>1e-9 or result['net_current_relative_error']>1e-9:
                        raise ValueError('Current continuity or isolated-volume current gate failed')
                    if label in ['zero','uniform']:
                        if result['joule_power_w']>max(1e-25,1e-12*result['source_power_scale_w']):
                            raise ValueError('Translation in uniform B or zero speed produced spurious current')
                    elif result['joule_power_w']<=0 or result['housing_force_n'][0]*speed>=0 or result['mechanical_joule_relative_balance']>.02:
                        raise ValueError('Passive drag/power balance failed')
                a=runs['forward'];r=runs['reverse']
                if not np.allclose(a['housing_force_n'],-np.array(r['housing_force_n']),rtol=1e-9,atol=1e-18) or not np.isclose(a['joule_power_w'],r['joule_power_w'],rtol=1e-9,atol=1e-24):
                    raise ValueError('Reverse-speed parity failed')
                level[name]=runs;output['levels'][str(h)]=level;save();print(h,name,a['joule_power_w'],a['housing_force_n'],flush=True)
        prior=output['levels'][str(args.meshes[-2])];fine=output['levels'][str(args.meshes[-1])]
        expected=rectangle_gradient_loss(housing['size_m'],args.sigma,args.speed)
        benchmark_error=abs(fine['closed']['gradient']['joule_power_w']/expected-1)
        output['independent_rectangular_gradient_benchmark']={'exact_loss_w':expected,'relative_error':benchmark_error,'gate':.05}
        if benchmark_error>.05:output['failures'].append('Independent rectangular gradient benchmark exceeds 5%')
        output['refinement']={}
        for name in ['closed','slotted']:
            a=prior[name]['forward'];b=fine[name]['forward']
            changes={'loss':abs(a['joule_power_w']/b['joule_power_w']-1),
                'force':float(np.linalg.norm(np.array(a['housing_force_n'])-b['housing_force_n'])/np.linalg.norm(b['housing_force_n']))}
            output['refinement'][name]=changes
            if max(changes.values())>.02:output['failures'].append(name+': refinement exceeds unchanged 2% gate')
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Closure implementation changed')
        if sha(origin/'summary.json')!=output['source_summary_sha256']:raise ValueError('Source report changed')
        output.update(status='failed' if output['failures'] else 'passed-finite-current-closure-low-rm-source-only',seconds=time.monotonic()-start)
        save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
