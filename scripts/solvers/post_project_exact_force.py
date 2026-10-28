#!/usr/bin/env python3
"""Exact piecewise-affine-field stress audit of completed static solver cases.

Checks six-face area coverage, three physical force paths, separate stator and
mover forces, bare/self-force floors and direct action/reaction. Removes only
surface quadrature error in the archived FEM field. It cannot fix a failed
nonlinear solve, spatial FEM error or a finite housing motion model.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from cut_surface_force import box_force,reflected_tetrahedra
from post_project_force import completed_field,sha
from post_project_balance import action_reaction,bounds
from project_static import check_force_paths,getdp_nonlinear_convergence,validate_mesh
from project_symmetry import quarter_model,validate_quarter_mesh
from read_vtu import _vector_mesh,clear_vector_cache
from source_snapshot import capture
from force_paths import force_paths


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--remote-air-paths',action='store_true',help='separate diagnostic: middle-gap planes and 1/2/3mm outer expansion; preserves near-surface failures and unchanged gates')
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('preserve the previous force report')
    summary=work/'summary.json';summary_sha=sha(summary)
    source,bare=completed_field(work,'bare');_,stack=completed_field(work,'stack')
    model=source['model'];quarter=bool(source.get('quarter_symmetry',False))
    if not model['stack']:raise ValueError('Need finite separate stator and mover bodies')
    solver_model=quarter_model(model) if quarter else model
    if quarter and source.get('solver_geometry_model')!=solver_model:raise ValueError('Changed quarter geometry metadata')
    validate_mesh(work/'project.msh',solver_model,source['air_radius_m'])
    if quarter:validate_quarter_mesh(work/'project.msh')
    convergence=None
    if source['backend']=='getdp':convergence=getdp_nonlinear_convergence(work/'stack')
    elif source['backend']=='elmer':
        from check_finite_plate import require_elmer_nonlinear_convergence
        convergence=require_elmer_nonlinear_convergence((work/'stack'/'solve.log').read_text())
    else:raise ValueError('Unrecognized static backend')
    if source.get('element_order',2) not in [1,2]:raise ValueError('Only affine B on linear tetrahedral cells is supported')
    surfaces_by_body={name:force_paths(model,name,args.remote_air_paths) for name in ['stator','mover']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    paths=[Path(__file__),*[Path(__file__).parent/name for name in ['cut_surface_force.py','post_project_balance.py',
           'post_project_force.py','project_static.py','project_symmetry.py','read_vtu.py','force_paths.py']]]
    sources=capture(args.output.parent,paths)
    report={'scope':__doc__,'status':'running','original_summary_status':source.get('status'),
            'original_summary_failures':source.get('failures'),'source_summary_sha256':summary_sha,
            'raw_field_sha256':{'bare':sha(bare),'stack':sha(stack)},'quarter_symmetry':quarter,
            'nonlinear_convergence':convergence,'cases':{},'action_reaction':{},'failures':[],
            'force_path_family':'remote-air' if args.remote_air_paths else 'near-interface',
            'physical_force_boxes_m':{name:{key:{'lower':low.tolist(),'upper':high.tolist()} for key,(low,high) in paths.items()} for name,paths in surfaces_by_body.items()},
            'source_snapshots':sources}
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    for label,path in [('bare',bare),('stack',stack)]:
        clear_vector_cache();stat=path.stat()
        vertices,fields,*_=_vector_mesh(str(path.resolve()),stat.st_mtime_ns,stat.st_size,'magnetic flux density e')
        if quarter:vertices,fields=reflected_tetrahedra(vertices,fields)
        bodies={}
        for name,objects in [('stator',model['stack']),('mover',model['magnets'])]:
            surfaces={}
            for clearance,(low,high) in surfaces_by_body[name].items():
                if np.linalg.norm(np.maximum(abs(low),abs(high)))>=0.95*source['air_radius_m']:
                    raise ValueError('Force box approaches the exterior boundary')
                result=box_force(vertices,fields,low,high);surfaces[str(clearance)]=result
                print(label,name,clearance,result['force_n'],flush=True)
            bodies[name]=surfaces
        report['cases'][label]=bodies;save()
        del vertices,fields
    for name in ['stator','mover']:
        controls={label:{'stack_force_by_clearance_n':{key:value['force_n'] for key,value in report['cases'][label][name].items()}}
                  for label in ['bare','stack']}
        for failure in check_force_paths(controls):report['failures'].append(name+': '+failure)
    for clearance in surfaces_by_body['stator']:
        check=action_reaction(report['cases']['stack']['stator'][clearance]['force_n'],report['cases']['stack']['mover'][clearance]['force_n'])
        report['action_reaction'][clearance]=check
        if not check['passed']:report['failures'].append(f'{clearance}: direct stator/mover action-reaction exceeds max(10nN, 2%)')
    if sha(summary)!=summary_sha or sha(bare)!=report['raw_field_sha256']['bare'] or sha(stack)!=report['raw_field_sha256']['stack']:
        raise ValueError('Original field inputs changed during audit')
    for path in paths:
        if sha(path)!=sources[str(path.resolve())]['sha256']:raise ValueError('Audit source changed while running')
    report['status']='failed' if report['failures'] else 'passed-exact-raw-field-stress-only';save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
