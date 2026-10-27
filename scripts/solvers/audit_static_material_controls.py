#!/usr/bin/env python3
"""Separate mesh, exterior-domain and integration controls for full vector bias.

Also compares with the independently assembled scalar-H equilibrium. Both
total and material-response maps are checked. Passing is only static numerical
qualification for this centred prototype with the declared reversible law.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_project_bare_map import observations
from compare_reduced_fields import completed_receipt
from ngsolve_reduced import total_field as scalar_field
from post_project_force import sha
from reduced_potential import source_field
from source_snapshot import capture


def control_request(reference,candidate,kind):
    keys={'mesh':{'mesh','fer_mesh','near_air_mesh'},'domain':{'far'},'quadrature':{'bonus_order'}}
    if kind not in keys:raise ValueError('Unknown static control')
    ignore={'mesh_only','static_only','save_every','max_dofs'}
    changes={k for k in set(reference)|set(candidate) if k not in ignore and reference.get(k)!=candidate.get(k)}
    if not changes or not changes<=keys[kind]:raise ValueError('Static control changes more than its declared parameter family')
    for key in changes:
        refined=candidate[key]<reference[key] if kind=='mesh' else candidate[key]>reference[key]
        if not refined:raise ValueError('Static control must refine, not coarsen')


def load(work):
    import ngsolve as ng
    report=json.loads((work/'summary.json').read_text());completed_receipt(report)
    if report['status'] not in ['completed-coupled-material-static-only','completed-nonlinear-ferrite-housing-motion-unqualified'] or report['failures']:
        raise ValueError('Need completed, successful static initial field')
    if report['profile']['start_offset_m']!=0:raise ValueError('Static comparison requires the centred pose')
    if report['version']!=ng.__version__ or sha(work/'mesh.vol')!=report['mesh_sha256'] or sha(work/'initial-reaction.sol')!=report['initial_solution_sha256']:
        raise ValueError('Static initial field, mesh or engine changed')
    mesh=ng.Mesh(str(work/'mesh.vol'));fes=ng.HCurl(mesh,order=report['request']['order'],nograds=True,dirichlet='outer')
    state=ng.GridFunction(fes);state.Load(str(work/'initial-reaction.sol'));reaction=ng.curl(state);source=source_field(report['model'])
    def evaluate(points):
        points=np.asarray(points);mapped=mesh(points[:,0],points[:,1],points[:,2])
        return source(points)+np.asarray(reaction(mapped)).reshape(-1,3)
    return report,evaluate


def force(path,work):
    report=json.loads(path.read_text());completed_receipt(report)
    if report['status']!='passed-static-material-force-integration-only' or report['failures'] or report['source_summary_sha256']!=sha(work/'summary.json'):
        raise ValueError('Incomplete or mismatched static force audit')
    degree=str(max(map(int,report['levels'])));delta=str(min(map(float,report['levels'][degree])))
    return np.array(report['levels'][degree][delta]['force_n'])


def compare(first,second,incident,tolerance):
    first=np.asarray(first);second=np.asarray(second);incident=np.asarray(incident)
    if first.shape!=second.shape or first.shape!=incident.shape or first.ndim!=2 or first.shape[1]!=3 or not np.isfinite([first,second,incident]).all():
        raise ValueError('Invalid static field maps')
    difference=float(np.linalg.norm(first-second));total=max(float(np.linalg.norm(first)),1e-10*np.sqrt(first.size))
    response=max(float(np.linalg.norm(first-incident)),1e-10*np.sqrt(first.size))
    return {'total_relative_error':difference/total,'response_relative_error':difference/response,
        'tolerance':tolerance,'passed':difference<=tolerance*min(total,response)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--baseline-force',type=Path,required=True)
    parser.add_argument('--reference-only',action='store_true',help='scalar-reference comparison only; does not qualify mesh/domain/quadrature')
    for name in ['mesh','domain','quadrature']:
        parser.add_argument('--'+name,type=Path);parser.add_argument('--'+name+'-force',type=Path)
    parser.add_argument('--scalar',type=Path,required=True);parser.add_argument('--scalar-force',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve all earlier static-control evidence')
    if not args.reference_only and any(getattr(args,k) is None for k in ['mesh','mesh_force','domain','domain_force','quadrature','quadrature_force']):
        parser.error('All isolated mesh/domain/quadrature jobs and forces required unless --reference-only')
    labels=['scalar'] if args.reference_only else ['mesh','domain','quadrature','scalar']
    base,evaluate=load(args.baseline);model=base['model'];source=source_field(model)
    maps=observations(model,64,24,both_sides=True);expected={k:evaluate(p) for k,p in maps.items()};f0=force(args.baseline_force,args.baseline)
    output={'status':'running','scope':__doc__,'checks':{},'failures':[],
        'input_hashes':{},'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    for label in ['baseline',*labels]:
        work=getattr(args,label);fp=getattr(args,label+'_force')
        output['input_hashes'][str(work/'summary.json')]=sha(work/'summary.json');output['input_hashes'][str(fp)]=sha(fp)
    save()
    try:
        for name in labels:
            work=getattr(args,name);candidate,field=scalar_field(work) if name=='scalar' else load(work)
            if candidate['model']!=model:raise ValueError('Different source/material models')
            if name!='scalar':control_request(base['request'],candidate['request'],name)
            tolerance=.05 if name=='scalar' else .02;checks={}
            for label,points in maps.items():
                checks[label]=compare(expected[label],field(points),source(points),tolerance)
                if not checks[label]['passed']:output['failures'].append(name+'/'+label)
            f1=force(getattr(args,name+'_force'),work);error=float(np.linalg.norm(f0-f1));limit=max(1e-8,tolerance*float(np.linalg.norm(f0)))
            checks['force']={'baseline_n':f0.tolist(),'candidate_n':f1.tolist(),'error_n':error,'limit_n':limit,'passed':error<=limit}
            if error>limit:output['failures'].append(name+'/force')
            output['checks'][name]=checks;save()
        for path,digest in output['input_hashes'].items():
            if sha(Path(path))!=digest:raise ValueError('Static-control input changed during audit')
        for path,entry in output['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Static-control implementation changed')
        output['status']='failed' if output['failures'] else ('passed-static-full-vector-scalar-reference-only' if args.reference_only else 'passed-static-full-vector-mesh-domain-quadrature-scalar-controls-only');save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
