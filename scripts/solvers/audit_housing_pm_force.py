#!/usr/bin/env python3
"""Independent PM/current interaction-force audit at a completed motion snapshot.

Reconstruct J from saved midpoint/endpoint fields, check the conductor force
against the archived Lorentz result, then calculate force on the PM array via
its magnetization and the free-space Biot-Savart field of those currents.
Opposite PM faces are integrated analytically. Body-current quadrature is
refined independently. No mover force is defined by negating a stator result.
This source-only, mu_r=1 PM/housing baseline excludes ferrite and winding.
"""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from ngsolve_housing_motion import moving_source,source_electric
from pm_current_force import array_force
from post_project_force import sha
from reduced_potential import source_field
from solver_threads import add_thread_option,runtime_metadata,threaded_main,positive_threads
from source_snapshot import capture


def conductor_sources(ng,mesh,current,order):
    rule=ng.IntegrationRule(ng.ET.TET,order)
    local=np.array([point.point[:3] for point in rule]);reference_weights=np.array([point.weight for point in rule])
    corners=ng.IntegrationRule(points=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)],weights=[1.,1.,1.,1.])
    coordinates=ng.CoefficientFunction((ng.x,ng.y,ng.z));points=[];weights=[];currents=[];count=0
    for element in mesh.Elements(ng.VOL):
        if element.mat!='conductor':continue
        if element.type!=ng.ET.TET:raise ValueError('This audit requires tetrahedral conductor elements')
        transform=mesh.GetTrafo(element)
        vertices=np.asarray(coordinates(transform(corners))).reshape(4,3)
        matrix=vertices[1:]-vertices[0];determinant=abs(float(np.linalg.det(matrix)))
        mapped=transform(rule);physical=np.asarray(coordinates(mapped)).reshape(-1,3)
        if determinant<=0 or np.max(abs(physical-(vertices[0]+local@matrix)))>1e-12:
            raise ValueError('Do not apply affine volume weights to a curved conductor cell')
        sampled=np.asarray(current(mapped),dtype=float).reshape(-1,3)
        if len(sampled)!=len(local) or not np.isfinite(sampled).all():raise ValueError('Invalid current quadrature samples')
        points.append(physical);currents.append(sampled);weights.append(reference_weights*determinant);count+=1
    if not count:raise ValueError('No conductor tetrahedra')
    return np.concatenate(points),np.concatenate(currents),np.concatenate(weights),count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--step',type=int);parser.add_argument('--body-orders',type=int,nargs='+')
    parser.add_argument('--green-workers',type=positive_threads,default=1)
    add_thread_option(parser);args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('Preserve earlier PM force audits')
    report=json.loads((work/'summary.json').read_text())
    if not report.get('command_receipt'):raise ValueError('Missing whole-motion receipt')
    completed_receipt(report)
    if report['status']!='completed-finite-housing-coupled-motion-unqualified' or report['failures']:
        raise ValueError('Do not postprocess failed/incomplete motion as accepted force evidence')
    if sha(work/'mesh.vol')!=report['mesh_sha256']:raise ValueError('Motion mesh changed')
    entry=next((item for item in report['saved_midpoints'] if item['step']==args.step),None) if args.step is not None else min(
        report['saved_midpoints'],key=lambda item:abs(report['steps'][item['step']]['source_offset_m']))
    if entry is None or sha(work/entry['file'])!=entry['sha256']:raise ValueError('Missing or changed midpoint field')
    step=entry['step'];record=report['steps'][step];request=report['request'];dt=report['profile']['dt_s']
    import ngsolve as ng
    if ng.__version__!=report['version']:raise ValueError('Reload fields with their pinned NGSolve version')
    mesh=ng.Mesh(str(work/'mesh.vol'));order=request['order']
    a_space=ng.HCurl(mesh,order=order,nograds=True,dirichlet='outer')
    p_space=ng.Compress(ng.H1(mesh,order=max(2,order+1),definedon=mesh.Materials('conductor')))
    fes=a_space*p_space;midpoint=ng.GridFunction(fes);midpoint.Load(str(work/entry['file']))
    endpoint=ng.GridFunction(fes)
    after=work/f'checkpoint-{step+1:05d}.sol';before=work/f'checkpoint-{step:05d}.sol'
    if after.exists():endpoint.Load(str(after));derivative=2/dt*(endpoint.components[0]-midpoint.components[0]);checkpoint=after
    elif step==0:derivative=2/dt*midpoint.components[0];checkpoint=None
    elif before.exists():endpoint.Load(str(before));derivative=2/dt*(midpoint.components[0]-endpoint.components[0]);checkpoint=before
    else:raise ValueError('A midpoint alone does not determine current; need an adjacent endpoint')
    offset=record['source_offset_m'];position=ng.Parameter(offset);bsource=moving_source(ng,report['model'],position)
    electric=source_electric(ng,bsource,request['speed'])
    current=(request['sigma']*(electric-derivative-2/dt*ng.grad(midpoint.components[1]))).Compile()
    original_order=2*(order+1)+request['bonus_order']
    levels=args.body_orders or [max(2,original_order-4),original_order]
    if len(levels)<2 or original_order not in levels or any(a>=b for a,b in zip(levels,levels[1:])):
        parser.error('Increasing body orders including the solved integration order are required')
    magnets=copy.deepcopy(report['model']['magnets'])
    for magnet in magnets:magnet['origin_m'][0]+=offset
    incident=source_field({'magnets':magnets})
    hashes={'summary':sha(work/'summary.json'),'mesh':sha(work/'mesh.vol'),'midpoint':sha(work/entry['file'])}
    if checkpoint:hashes['endpoint']=sha(checkpoint)
    output={'status':'running','scope':__doc__,'step':step,'source_offset_m':offset,'input_hashes':hashes,
        'execution':dict(runtime_metadata(),green_workers=args.green_workers),'levels':{},'failures':[],
        'source_snapshots':capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['pm_current_force.py','ngsolve_housing_motion.py','ngsolve_reduced.py','solver_threads.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for degree in levels:
            points,j,weights,cells=conductor_sources(ng,mesh,current,degree)
            volume=float(weights.sum())
            if abs(volume/report['conductor_volume_m3']-1)>1e-9:raise ValueError('Conductor quadrature volume changed')
            weighted=j*weights[:,None];housing_force=np.cross(weighted,incident(points)).sum(axis=0)
            loss=float(np.sum(weights*np.sum(j*j,axis=1))/request['sigma'])
            individual=array_force(magnets,points,weighted,args.green_workers);mover=individual.sum(axis=0)
            difference=float(np.linalg.norm(mover+housing_force));limit=max(1e-8,.02*max(float(np.linalg.norm(mover)),float(np.linalg.norm(housing_force))))
            total_housing=housing_force+np.array(record['housing_self_force_n'])
            total_difference=float(np.linalg.norm(mover+total_housing))
            output['levels'][str(degree)]={'current_points':len(points),'conductor_cells':cells,'volume_m3':volume,
                'housing_source_force_n':housing_force.tolist(),'pm_forces_n':individual.tolist(),'pm_array_force_n':mover.tolist(),
                'housing_total_force_n':total_housing.tolist(),'total_action_reaction_error_n':total_difference,
                'joule_power_w':loss,'action_reaction_error_n':difference,'action_reaction_limit_n':limit,
                'passed':difference<=limit and total_difference<=limit}
            if difference>limit:output['failures'].append(str(degree)+': independent PM/conductor interaction forces disagree')
            if total_difference>limit:output['failures'].append(str(degree)+': total PM/housing action-reaction gate failed')
            if degree==original_order:
                expected=np.array(record['housing_source_interaction_force_n'])
                if np.linalg.norm(housing_force-expected)>max(1e-10,1e-8*np.linalg.norm(expected)) or not np.isclose(loss,record['joule_power_w'],rtol=1e-8,atol=1e-12):
                    raise ValueError('Reloaded current does not reproduce the archived conductor observables')
            save();print('body quadrature',degree,'PM force',mover.tolist(),'imbalance',difference,flush=True)
        a=output['levels'][str(levels[-2])];b=output['levels'][str(levels[-1])]
        change=float(np.linalg.norm(np.array(a['pm_array_force_n'])-b['pm_array_force_n']))
        limit=max(1e-8,.02*float(np.linalg.norm(b['pm_array_force_n'])))
        output['quadrature_refinement']={'absolute_change_n':change,'limit_n':limit,'passed':change<=limit}
        if change>limit:output['failures'].append('Independent PM force body quadrature did not converge')
        if sha(work/'summary.json')!=hashes['summary'] or sha(work/entry['file'])!=hashes['midpoint'] or (checkpoint and sha(checkpoint)!=hashes['endpoint']):
            raise ValueError('Motion source changed during force audit')
        for name,entry in output['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('PM force implementation changed during audit')
        output['status']='failed' if output['failures'] else 'passed-independent-pm-current-force-snapshot-only';save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
