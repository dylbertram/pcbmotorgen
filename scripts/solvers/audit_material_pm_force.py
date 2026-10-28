#!/usr/bin/env python3
"""Independent current-plus-magnetization PM-force audit of a nonlinear snapshot.

Uses saved midpoint/endpoint fields, constitutive magnetization, analytical
Biot-Savart face kernels and separately refined dipole-kernel derivatives.
No PM force is assigned from negative stator force. Provisional reversible
material laws and fixed axial mu_r=1 PMs; not a hardware accuracy certificate.
"""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from ngsolve_material_motion import translated_source
from ngsolve_housing_motion import source_electric
from pm_current_force import array_force,array_magnetization_force
from post_project_force import sha
from reduced_potential import source_field
from solver_threads import add_thread_option,positive_threads,runtime_metadata,threaded_main
from source_snapshot import capture
from vector_material import magnetization_b
from volume_field_quadrature import sample


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--step',type=int);parser.add_argument('--degrees',type=int,nargs='+',default=[6,10])
    parser.add_argument('--deltas',type=float,nargs='+',default=[1e-7,5e-8]);parser.add_argument('--green-workers',type=positive_threads,default=1)
    add_thread_option(parser);args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('Preserve previous nonlinear force audits')
    if len(args.degrees)<2 or len(args.deltas)<2 or any(a>=b for a,b in zip(args.degrees,args.degrees[1:])) or any(a<=b for a,b in zip(args.deltas,args.deltas[1:])) or min(args.deltas)<=0:
        parser.error('Increasing volume rules and decreasing positive derivative steps required')
    report=json.loads((work/'summary.json').read_text())
    if not report.get('command_receipt'):raise ValueError('Missing complete nonlinear-motion receipt')
    completed_receipt(report)
    if report['status']!='completed-nonlinear-ferrite-housing-motion-unqualified' or report['failures']:
        raise ValueError('Do not turn a failed/incomplete trajectory into force evidence')
    request=report['request'];dt=report['profile']['dt_s']
    available={int(path.stem.split('-')[-1]):path for path in work.glob('midpoint-*.sol')}
    step=args.step if args.step is not None else min(available,key=lambda i:abs(report['steps'][i]['source_offset_m']))
    if step not in available:raise ValueError('Requested midpoint was not archived')
    row=report['steps'][step];midfile=available[step]
    import ngsolve as ng
    if ng.__version__!=report['version'] or sha(work/'mesh.vol')!=report['mesh_sha256']:raise ValueError('Nonlinear mesh/version changed')
    mesh=ng.Mesh(str(work/'mesh.vol'));order=request['order']
    a=ng.HCurl(mesh,order=order,nograds=True,dirichlet='outer')
    p=ng.Compress(ng.H1(mesh,order=max(2,order+1),definedon=mesh.Materials('conductor')))
    fes=a*p;midpoint=ng.GridFunction(fes);midpoint.Load(str(midfile));endpoint=ng.GridFunction(fes)
    before=work/f'checkpoint-{step:05d}.sol';after=work/f'checkpoint-{step+1:05d}.sol'
    derivative=ng.GridFunction(fes)
    if before.exists():
        endpoint.Load(str(before));rate=2/dt*(midpoint.vec.FV().NumPy()[:a.ndof]-endpoint.vec.FV().NumPy()[:a.ndof]);adjacent=before
    elif after.exists():
        endpoint.Load(str(after));rate=2/dt*(endpoint.vec.FV().NumPy()[:a.ndof]-midpoint.vec.FV().NumPy()[:a.ndof]);adjacent=after
    elif step==0:
        initial=ng.GridFunction(a);initial.Load(str(work/'initial-reaction.sol'))
        rate=2/dt*(midpoint.vec.FV().NumPy()[:a.ndof]-initial.vec.FV().NumPy());adjacent=work/'initial-reaction.sol'
    else:raise ValueError('Need an adjacent endpoint to reconstruct physical current')
    derivative.vec.FV().NumPy()[:a.ndof]=rate
    offset=row['source_offset_m'];positions=[ng.Parameter(offset),ng.Parameter(0.),ng.Parameter(0.)]
    bsource=translated_source(ng,report['model'],positions);gradients=[bsource.Diff(x).Compile() for x in positions]
    current=(request['sigma']*(source_electric(ng,bsource,request['speed'])-derivative.components[0]-2/dt*ng.grad(midpoint.components[1]))).Compile()
    moments=[]
    for material in report['model']['stack']:
        if material['mu_r']<=1 or material['name']=='housing':continue
        moment=magnetization_b(ng,bsource+ng.curl(midpoint.components[0]),material['mu_r'],material['bsat_t']).Compile()
        force=ng.CoefficientFunction(tuple(-ng.InnerProduct(moment,g) for g in gradients)).Compile()
        moments.append((material['name'],moment,force))
    magnets=copy.deepcopy(report['model']['magnets'])
    for magnet in magnets:magnet['origin_m'][0]+=offset
    incident=source_field({'magnets':magnets})
    original_order=2*(order+1)+request['bonus_order']
    if original_order not in args.degrees:raise ValueError('Include the solved integration rule for current/force roundtrip checks')
    hashes={'summary':sha(work/'summary.json'),'mesh':sha(work/'mesh.vol'),'midpoint':sha(midfile),'endpoint':sha(adjacent)}
    output={'status':'running','scope':__doc__,'step':step,'source_offset_m':offset,'input_hashes':hashes,
        'execution':dict(runtime_metadata(),green_workers=args.green_workers),'levels':{},'failures':[],
        'source_snapshots':capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['pm_current_force.py','vector_material.py','volume_field_quadrature.py','ngsolve_material_motion.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for degree in args.degrees:
            points,j,weights=sample(ng,mesh,current,'conductor',degree)
            housing=np.cross(j*weights[:,None],incident(points)).sum(axis=0)
            loss=float(np.sum(weights*np.sum(j*j,axis=1))/request['sigma'])
            force_current=array_force(magnets,points,j*weights[:,None],args.green_workers).sum(axis=0)
            material_source=np.zeros(3);mp=[];mw=[]
            for region,magnetization,force_cf in moments:
                p0,m0,w0=sample(ng,mesh,magnetization,region,degree);mp.append(p0);mw.append(m0*w0[:,None])
                material_source+=np.asarray(ng.Integrate(force_cf,mesh,definedon=mesh.Materials(region),order=degree)).reshape(3)
            mp=np.concatenate(mp);mw=np.concatenate(mw);level={}
            if degree==original_order:
                expected=np.array(row['housing_source_force_n']);material_expected=np.array(row['material_source_force_n'])
                if np.linalg.norm(housing-expected)>max(1e-10,1e-8*np.linalg.norm(expected)) or not np.isclose(loss,row['joule_power_w'],rtol=1e-8,atol=1e-12):
                    raise ValueError('Reloaded current differs from archived observables')
                if np.linalg.norm(material_source-material_expected)>max(1e-10,1e-8*np.linalg.norm(material_expected)):
                    raise ValueError('Reloaded material state differs from source-work force')
            for delta in args.deltas:
                force_material=array_magnetization_force(magnets,mp,mw,delta,args.green_workers).sum(axis=0)
                mover=force_current+force_material;stator=housing+material_source
                error=float(np.linalg.norm(mover+stator));limit=max(1e-8,.02*max(float(np.linalg.norm(mover)),float(np.linalg.norm(stator))))
                level[str(delta)]={'current_pm_force_n':force_current.tolist(),'material_pm_force_n':force_material.tolist(),
                    'pm_array_force_n':mover.tolist(),'stator_source_force_n':stator.tolist(),'joule_power_w':loss,
                    'force_balance_error_n':error,'limit_n':limit,'passed':error<=limit}
                if error>limit:output['failures'].append(f'{degree}/{delta}: independent total PM force disagrees')
                output['levels'][str(degree)]=level;save();print(degree,delta,'PM force',mover.tolist(),'balance',error,flush=True)
        fine=np.array(output['levels'][str(args.degrees[-1])][str(args.deltas[-1])]['pm_array_force_n'])
        volume=np.array(output['levels'][str(args.degrees[-2])][str(args.deltas[-1])]['pm_array_force_n'])
        derivative_force=np.array(output['levels'][str(args.degrees[-1])][str(args.deltas[-2])]['pm_array_force_n'])
        limit=max(1e-8,.02*float(np.linalg.norm(fine)))
        output['refinement']={'volume_change_n':float(np.linalg.norm(volume-fine)),'derivative_change_n':float(np.linalg.norm(derivative_force-fine)),'limit_n':limit}
        if max(np.linalg.norm(volume-fine),np.linalg.norm(derivative_force-fine))>limit:output['failures'].append('Total nonlinear force integration did not converge')
        if sha(work/'summary.json')!=hashes['summary'] or sha(midfile)!=hashes['midpoint'] or sha(adjacent)!=hashes['endpoint']:
            raise ValueError('Nonlinear snapshot changed during audit')
        for name,entry in output['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Nonlinear force audit implementation changed')
        output['status']='failed' if output['failures'] else 'passed-nonlinear-current-material-pm-force-snapshot-only';save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
