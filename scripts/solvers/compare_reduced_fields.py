#!/usr/bin/env python3
"""Controlled material-response field/force comparisons for fixed static cases.

Checks both total B and the FEM material response, so a common large analytical
source cannot hide reaction-field error. Different-backend agreement may use a
shared initial guess and mesh; that fact is reported, not called cold-start
independence. No hardware, winding-current or motion qualification is implied.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_project_bare_map import observations
from ngsolve_reduced import load_solution, total_field
from post_project_force import sha
from post_reduced_force import case_field
from project_symmetry import mirrored_sample
from read_vtu import sample_vector
from reduced_inputs import validate_reduced_inputs, same_model
from reduced_potential import source_field
from source_snapshot import capture

CONTROLS=['mesh_m','gap_mesh_m','observation_mesh_m','physical_observation_band_m','far_mesh_m','air_radius_m','z_stretch','quarter_symmetry']


def completed_receipt(report):
    path=report.get('command_receipt')
    if path:
        receipt=json.loads(Path(path).read_text())
        if receipt.get('status')!='completed' or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0:
            raise ValueError('Whole-job supervisor did not complete successfully')


def field_case(work):
    report=json.loads((work/'summary.json').read_text());completed_receipt(report)
    incident=source_field(report['model'])
    if report.get('backend')=='NGSolve':
        _,metadata,_,_,_=load_solution(work)
        receipt=json.loads(Path(metadata['command_receipt']).read_text());cmd=receipt['command']
        origin=Path(cmd[cmd.index('--source-work')+1]);source=json.loads((origin/'summary.json').read_text())
        if sha(origin/'summary.json')!=report['source_summary_sha256'] or report['model']!=source['model']:
            raise ValueError('Independent field no longer matches its original physical inputs')
        validate_reduced_inputs(origin,source)
        _,evaluate=total_field(work)
        backend='NGSolve'
    else:
        source=report;validate_reduced_inputs(work,source);field=case_field(work,source,'stack')
        reader=mirrored_sample if source['quarter_symmetry'] else sample_vector
        evaluate=lambda p:incident(p)+reader(field,p)
        backend='GetDP'
    return report,source,evaluate,backend


def validate_controls(first,second,kind):
    if not same_model(first['model'],second['model']) or first['linear_material']!=second['linear_material']:
        raise ValueError('Different physical model or constitutive mode')
    if kind=='agreement':
        if any(first[k]!=second[k] for k in CONTROLS):raise ValueError('Backend comparison changed mesh/domain controls')
        return
    changed={key for key in CONTROLS if first[key]!=second[key]}
    expected={'mesh':{'mesh_m','gap_mesh_m','observation_mesh_m'},'far':{'far_mesh_m'},'domain':{'air_radius_m'}}[kind]
    if changed!=expected:raise ValueError('Resolution axes were not changed independently')
    if kind=='mesh' and any(second[k]>=first[k] for k in expected):raise ValueError('Near mesh was not refined')
    if kind=='far' and second['far_mesh_m']>=first['far_mesh_m']:raise ValueError('Far mesh was not refined')
    if kind=='domain' and second['air_radius_m']<=first['air_radius_m']:raise ValueError('Domain was not expanded')


def load_force(path,field_summary_sha):
    report=json.loads(path.read_text());completed_receipt(report)
    if report.get('status') not in ['passed-independent-total-field-surface-and-quadrature-only','passed-total-field-surface-and-quadrature-only'] or report.get('failures')!=[]:
        raise ValueError('Force surface/quadrature controls are incomplete or failed')
    if report['source_hashes']['summary']!=field_summary_sha:raise ValueError('Force audit belongs to a different field')
    return report['levels'][str(max(map(int,report['levels'])))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-work',type=Path,required=True);parser.add_argument('--second-work',type=Path,required=True)
    parser.add_argument('--kind',choices=['agreement','mesh','far','domain'],required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--first-force',type=Path);parser.add_argument('--second-force',type=Path)
    args=parser.parse_args();raw_path=args.output.with_suffix('.npz')
    if args.output.exists() or raw_path.exists():parser.error('Preserve earlier comparisons')
    if bool(args.first_force)!=bool(args.second_force):parser.error('Both force audits are required together')
    first=args.first_work.resolve();second=args.second_work.resolve()
    a,sa,fa,ba=field_case(first);b,sb,fb,bb=field_case(second)
    validate_controls(sa,sb,args.kind)
    if args.kind!='agreement' and (ba!=bb or a.get('order')!=b.get('order') or a.get('bonus_integration_order')!=b.get('bonus_integration_order')):
        raise ValueError('Basis, backend or material quadrature changed during a mesh/boundary control')
    tolerance=.05 if args.kind=='agreement' else .02
    source=source_field(a['model']);records={};raw={};failures=[]
    for i,(label,p) in enumerate(observations(a['model'],64,24,both_sides=True).items()):
        x=fa(p);y=fb(p);background=source(p);rx=x-background;ry=y-background
        if not np.isfinite([x,y,rx,ry]).all() or np.linalg.norm(ry)<=1e-12:raise ValueError('Unresolved/nonfinite material-response probes')
        total=float(np.linalg.norm(x-y)/np.linalg.norm(y));reaction=float(np.linalg.norm(rx-ry)/np.linalg.norm(ry))
        records[label]={'total_field_relative_error':total,'material_response_relative_error':reaction,'passed':total<=tolerance and reaction<=tolerance}
        if not records[label]['passed']:failures.append(label+': field change/agreement gate failed')
        raw[f'points_{i}']=p;raw[f'first_total_{i}']=x;raw[f'second_total_{i}']=y
        print(label,records[label],flush=True)
    force_checks={}
    if args.first_force:
        x=load_force(args.first_force,sha(first/'summary.json'));y=load_force(args.second_force,sha(second/'summary.json'))
        for body in ['stator','mover']:
            force_checks[body]={}
            if set(x['stack'][body])!=set(y['stack'][body]):raise ValueError('Different physical force paths')
            for key in x['stack'][body]:
                u=np.array(x['stack'][body][key]['force_n']);v=np.array(y['stack'][body][key]['force_n'])
                error=float(np.linalg.norm(u-v));limit=max(1e-8,tolerance*float(np.linalg.norm(v)))
                force_checks[body][key]={'absolute_change_n':error,'limit_n':limit,'passed':error<=limit}
                if error>limit:failures.append(body+' '+key+': force change/agreement gate failed')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with raw_path.open('xb') as stream:np.savez_compressed(stream,**raw)
    report={'status':'failed' if failures else 'passed-static-'+args.kind+'-comparison-only','scope':__doc__,
        'kind':args.kind,'gate':tolerance,'backends':[ba,bb],'different_backends':ba!=bb,
        'shared_initial_guess':bool(a.get('shared_initial_guess') or b.get('shared_initial_guess') or a.get('initial_guess') or b.get('initial_guess')),
        'same_mesh':a['mesh_sha256']==b['mesh_sha256'],'source_summary_sha256':[sha(first/'summary.json'),sha(second/'summary.json')],
        'controls':[{k:s[k] for k in CONTROLS} for s in [sa,sb]],'fields':records,'force_checks':force_checks,'failures':failures,
        'raw_probe_sha256':sha(raw_path),'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if args.first_force:report['force_report_sha256']=[sha(args.first_force),sha(args.second_force)]
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
