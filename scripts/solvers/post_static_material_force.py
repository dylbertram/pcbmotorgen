#!/usr/bin/env python3
"""PM force from archived static nonlinear material magnetization.

Runs on either scalar-H or vector-A fields; the common force integration is
disclosed. It checks material quadrature and independent source-coordinate
derivative refinement. No failed force floor is subtracted.
"""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np

from ngsolve_reduced import source_coefficient
from pm_current_force import array_magnetization_force
from post_project_force import sha
from solver_threads import add_thread_option,runtime_metadata,threaded_main,positive_threads
from source_snapshot import capture
from vector_material import magnetization_b,MU0
from volume_field_quadrature import sample


def mirror(points,values,weights,quarter):
    if not quarter:return points,values,weights
    p=[];v=[];w=[]
    for x,y in [(1,1),(-1,1),(1,-1),(-1,-1)]:
        signs=np.array([x,y,1.]);p.append(points*signs);v.append(values*signs);w.append(weights)
    return np.concatenate(p),np.concatenate(v),np.concatenate(w)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scalar-work',type=Path);group.add_argument('--vector-work',type=Path)
    group.add_argument('--coupled-work',type=Path,help='initial static field from a completed ferrite/housing job')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--degrees',type=int,nargs='+',default=[6,8])
    parser.add_argument('--deltas',type=float,nargs='+',default=[1e-7,5e-8]);parser.add_argument('--green-workers',type=positive_threads,default=1)
    add_thread_option(parser);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve prior static material-force audits')
    if len(args.degrees)<2 or len(args.deltas)<2 or any(a>=b for a,b in zip(args.degrees,args.degrees[1:])) or any(a<=b for a,b in zip(args.deltas,args.deltas[1:])) or min(args.deltas)<=0:
        parser.error('Increasing volume rules and decreasing positive derivative steps required')
    work=(args.scalar_work or args.vector_work or args.coupled_work).resolve()
    if args.scalar_work:
        from ngsolve_reduced import load_solution
        ng,source,mesh,fes,solution=load_solution(work);backend='scalar-H'
    elif args.vector_work:
        from ngsolve_vector_static import load
        ng,source,mesh,fes,solution=load(work);backend='vector-A'
    else:
        import ngsolve as ng
        from compare_reduced_fields import completed_receipt
        source=json.loads((work/'summary.json').read_text());completed_receipt(source)
        if source['status'] not in ['completed-coupled-material-static-only','completed-nonlinear-ferrite-housing-motion-unqualified'] or source['failures']:
            raise ValueError('Need a completed coupled material job, not an incomplete initial state')
        if source['version']!=ng.__version__ or sha(work/'mesh.vol')!=source['mesh_sha256']:
            raise ValueError('Coupled initial-field version or mesh changed')
        if source.get('initial_solution_sha256') and sha(work/'initial-reaction.sol')!=source['initial_solution_sha256']:
            raise ValueError('Coupled initial field changed')
        mesh=ng.Mesh(str(work/'mesh.vol'));fes=ng.HCurl(mesh,order=source['request']['order'],nograds=True,dirichlet='outer')
        solution=ng.GridFunction(fes);solution.Load(str(work/'initial-reaction.sol'));backend='vector-A-coupled-geometry-initial'
        source=copy.deepcopy(source);source['quarter_symmetry']=False
        source['solver_geometry_model']={'stack':[m for m in source['model']['stack'] if m['mu_r']>1]}
        for magnet in source['model']['magnets']:magnet['origin_m'][0]+=source['profile']['start_offset_m']
    bsource=source_coefficient(ng,source['model']).Compile();fields=[]
    for material in source['solver_geometry_model']['stack']:
        mu=material['mu_r'];bsat=material['bsat_t']
        if args.vector_work or args.coupled_work:
            magnetization=magnetization_b(ng,bsource+ng.curl(solution),mu,bsat)
        else:
            h=bsource/MU0-ng.grad(solution);squared=ng.InnerProduct(h,h)
            if mu==1:magnetization=ng.CoefficientFunction((0.,0.,0.))
            elif bsat is None:magnetization=(mu-1)*h
            else:
                knee=bsat/(MU0*(mu-1));radius=ng.sqrt(ng.IfPos(squared,squared,1.))
                magnetization=ng.IfPos(squared-knee*knee,bsat/(MU0*radius),mu-1)*h
        fields.append((material['name'],magnetization.Compile()))
    output={'status':'running','scope':__doc__,'backend':backend,'source_summary_sha256':sha(work/'summary.json'),
        'source_solution_sha256':sha(work/('psi.sol' if args.scalar_work else 'initial-reaction.sol' if args.coupled_work else 'reaction.sol')),
        'execution':dict(runtime_metadata(),green_workers=args.green_workers),'levels':{},'failures':[],
        'source_snapshots':capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['vector_material.py','pm_current_force.py','volume_field_quadrature.py','ngsolve_reduced.py','ngsolve_vector_static.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for degree in args.degrees:
            points=[];moments=[]
            for region,field in fields:
                p,m,w=sample(ng,mesh,field,region,degree)
                p,m,w=mirror(p,m,w,source['quarter_symmetry']);points.append(p);moments.append(m*w[:,None])
            points=np.concatenate(points);moments=np.concatenate(moments);level={}
            for delta in args.deltas:
                individual=array_magnetization_force(source['model']['magnets'],points,moments,delta,args.green_workers)
                level[str(delta)]={'force_n':individual.sum(axis=0).tolist(),'per_pm_force_n':individual.tolist(),'source_points':len(points)}
                output['levels'][str(degree)]=level;save();print(degree,delta,level[str(delta)]['force_n'],flush=True)
        fine=output['levels'][str(args.degrees[-1])][str(args.deltas[-1])]['force_n'];fine=np.array(fine)
        limit=max(1e-8,.02*float(np.linalg.norm(fine)))
        volume=np.array(output['levels'][str(args.degrees[-2])][str(args.deltas[-1])]['force_n'])
        derivative=np.array(output['levels'][str(args.degrees[-1])][str(args.deltas[-2])]['force_n'])
        output['refinements']={'volume_absolute_change_n':float(np.linalg.norm(volume-fine)),
            'derivative_absolute_change_n':float(np.linalg.norm(derivative-fine)),'limit_n':limit}
        if max(np.linalg.norm(volume-fine),np.linalg.norm(derivative-fine))>limit:output['failures'].append('Static force quadrature/derivative gate failed')
        for name,entry in output['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Static force implementation changed')
        if sha(work/'summary.json')!=output['source_summary_sha256']:raise ValueError('Static response report changed')
        output['status']='failed' if output['failures'] else 'passed-static-material-force-integration-only';save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
