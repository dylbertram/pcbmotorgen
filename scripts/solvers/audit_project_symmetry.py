#!/usr/bin/env python3
"""Recompute full/quarter scalar static parity from completed raw fields.

Checks the same physical model, mesh controls and air radius. Reconstructs full
closed-air force surfaces without quarter-force scaling. This is symmetry
parity, not separate mesh/domain convergence or a finite moving-housing result.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from maxwell_stress import box_faces,force
from post_project_force import completed_field
from project_static import check_force_paths,getdp_nonlinear_convergence,validate_mesh
from project_symmetry import quarter_model,validate_quarter_mesh,mirrored_sample
from read_vtu import sample_vector,clear_vector_cache
from source_snapshot import capture
from solver_resources import getdp_resources


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def match_settings(full,quarter):
    if full.get('quarter_symmetry',False) or not quarter.get('quarter_symmetry',False):raise ValueError('Need full then quarter jobs')
    if full.get('backend')!='getdp' or quarter.get('backend')!='getdp':raise ValueError('Symmetry audit requires scalar GetDP jobs')
    for key in ['model','mesh_m','gap_mesh_m','air_radius_m']:
        if full[key]!=quarter[key]:raise ValueError(f'Different physical model or numerical settings: {key}')
    if full.get('z_stretch',1)!=quarter.get('z_stretch',1):raise ValueError('Different mesh coordinate transforms')
    if full.get('far_mesh_m',full['air_radius_m']/6)!=quarter.get('far_mesh_m',quarter['air_radius_m']/6):
        raise ValueError('Different far-air mesh controls')
    if full.get('magnet_face_mesh_m')!=quarter.get('magnet_face_mesh_m'):raise ValueError('Different PM-interface mesh controls')
    if full.get('magnet_face_band_m')!=quarter.get('magnet_face_band_m'):raise ValueError('Different PM-interface band controls')


def vector_errors(full_field,quarter_field,full_force,quarter_force):
    a=np.asarray(full_field);b=np.asarray(quarter_field);f=np.asarray(full_force);g=np.asarray(quarter_force)
    if a.shape!=b.shape or a.ndim!=2 or a.shape[1]!=3 or f.shape!=g.shape or f.ndim!=2 or f.shape[1]!=3 or not all(np.isfinite(v).all() for v in [a,b,f,g]):
        raise ValueError('Malformed parity fields/forces')
    norm=float(np.linalg.norm(a))
    if norm<=0:raise ValueError('Missing independent nonzero reference field')
    field_error=float(np.linalg.norm(a-b)/norm)
    difference=np.linalg.norm(f-g,axis=1);limits=np.maximum(1e-8,0.02*np.linalg.norm(f,axis=1))
    return {'field_vector_relative_error':field_error,'force_vector_absolute_errors_n':difference.tolist(),
            'force_vector_limits_n':limits.tolist(),'passed':bool(field_error<=0.02 and np.all(difference<=limits))}


def load_job(work,quarter):
    summary=json.loads((work/'summary.json').read_text())
    if summary.get('status')!='comparison-only' or summary.get('failures')!=[]:
        raise ValueError(f'Incomplete or failed static job: {work}')
    model=summary['model'];solver_model=quarter_model(model) if quarter else model
    if quarter and summary.get('solver_geometry_model')!=solver_model:raise ValueError('Quarter geometry metadata changed')
    validate_mesh(work/'project.msh',solver_model,summary['air_radius_m'])
    if quarter:validate_quarter_mesh(work/'project.msh')
    nonlinear=getdp_nonlinear_convergence(work/'stack')
    if check_force_paths(summary['runs']):raise ValueError('Original force-path or bare control failed')
    fields={};hashes={};orders=set()
    for mode in ['bare','stack']:
        _,path=completed_field(work,mode)
        if path.suffix!='.pos':raise ValueError('Unexpected non-scalar raw field')
        fields[mode]=path
        formulation=work/mode/'project.pro'
        orders.add(2 if 'BF_Node_2E' in formulation.read_text() else 1)
        hashes[mode]={'field_sha256':sha(path),'formulation_sha256':sha(formulation),
                      'receipt_sha256':sha(work/mode/'solve.log.command.json')}
    if len(orders)!=1:raise ValueError('Element order changed between bare and stack')
    return summary,fields,hashes,orders.pop(),nonlinear


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',type=Path,required=True)
    parser.add_argument('--quarter',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('preserve the previous audit; choose a new output')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    paths=[Path(__file__),*[Path(__file__).parent/name for name in ['project_symmetry.py','project_static.py',
           'post_project_force.py','read_vtu.py','maxwell_stress.py','solver_resources.py']]]
    sources=capture(args.output.parent,paths)
    full=args.full.resolve();quarter=args.quarter.resolve()
    a,fields_a,hashes_a,order_a,residual_a=load_job(full,False)
    b,fields_b,hashes_b,order_b,residual_b=load_job(quarter,True)
    match_settings(a,b)
    if order_a!=order_b:raise ValueError('Different scalar element orders')
    n=a.get('force_subdivisions',64)
    if b.get('force_subdivisions',64)!=n:raise ValueError('Different original force quadrature')
    model=a['model'];left=min(o['origin_m'][0] for o in model['magnets']);right=max(o['origin_m'][0]+o['size_m'][0] for o in model['magnets'])
    observations=np.column_stack([np.linspace(left,right,61),np.full(61,model['array_centre_mm'][1]*1e-3),np.full(61,model['pcb_thickness_m']/2)])
    length,width=model['footprint_m'];bottom=min(o['origin_m'][2] for o in model['stack'])
    recomputed={};comparisons={};failures=[]
    for label,summary,fields,reader in [('full',a,fields_a,sample_vector),('quarter',b,fields_b,mirrored_sample)]:
        modes={}
        for mode in ['bare','stack']:
            clear_vector_cache();sampled=reader(fields[mode],observations,'magnetic flux density e');forces={}
            for clearance in [0.0001,0.0002,0.0003]:
                faces=box_faces(length/2+clearance,bottom-clearance,clearance,n,halfdepth=width/2+clearance)
                value=force(faces,[reader(fields[mode],points,'magnetic flux density e') for points,_,_ in faces])
                expected=np.asarray(summary['runs'][mode]['stack_force_by_clearance_n'][str(clearance)])
                if np.linalg.norm(value-expected)>1e-8:raise ValueError('Archived force does not match the raw field')
                forces[str(clearance)]=value.tolist()
            modes[mode]={'field':sampled,'stack_force_by_clearance_n':forces}
        if check_force_paths(modes):raise ValueError('Recomputed force-path/bare control failed')
        recomputed[label]=modes
    for mode in ['bare','stack']:
        f=recomputed['full'][mode];q=recomputed['quarter'][mode]
        if mode=='bare':
            # Near-zero bare forces are judged by each job's absolute/stack
            # control above, not relative to another near-zero artifact.
            result=vector_errors(f['field'],q['field'],[[0,0,0]],[[0,0,0]])
        else:result=vector_errors(f['field'],q['field'],list(f['stack_force_by_clearance_n'].values()),list(q['stack_force_by_clearance_n'].values()))
        comparisons[mode]=result
        if not result['passed']:failures.append(f'{mode}: full/quarter parity exceeds unchanged 2% gates')
    for path in paths:
        if sha(path)!=sources[str(path.resolve())]['sha256']:raise ValueError('Audit source changed during validation; preserve and rerun')
    report={'scope':__doc__,'status':'failed' if failures else 'passed-full-quarter-static-parity','failures':failures,
            'full_summary_sha256':sha(full/'summary.json'),'quarter_summary_sha256':sha(quarter/'summary.json'),
            'original_fields':{'full':hashes_a,'quarter':hashes_b},'element_order':order_a,
            'nonlinear_convergence':{'full':residual_a,'quarter':residual_b},'comparisons':comparisons,
            'solver_reported_resources':{label:{mode:getdp_resources((work/mode/'solve.log').read_text()) for mode in ['bare','stack']}
                                         for label,work in [('full',full),('quarter',quarter)]},
            'source_snapshots':sources}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report,indent=2))
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
