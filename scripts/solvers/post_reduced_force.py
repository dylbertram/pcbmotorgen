#!/usr/bin/env python3
"""Audit TOTAL analytical-source plus FEM-response forces without floor removal.

Passing this audit covers force surfaces and triangle quadrature only. Mesh,
source-input, far-air, domain and independent-backend comparisons are separate.
Bare-only studies remain unqualified diagnostics, without an invented relative
material-force gate. Failed/partial jobs cannot provide a usable response field.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from force_paths import force_paths
from post_project_balance import action_reaction
from post_project_force import sha
from project_static import check_force_paths, getdp_nonlinear_convergence, validate_mesh
from project_symmetry import validate_quarter_mesh
from read_vtu import _vector_mesh, clear_vector_cache
from reduced_potential import source_field, response_model
from cut_surface_force import reflected_tetrahedra
from source_snapshot import capture
from total_field_stress import box_force
from reduced_inputs import validate_reduced_inputs


def case_field(work,source,name):
    if source.get('method')!='analytic-source-reduced-scalar-potential' or source.get('status')!='completed-reduced-response-fields-unqualified' or source.get('failures')!=[]:
        raise ValueError('Need a completed reduced-response job, not a partial/failed trial')
    if sha(work/'project.msh')!=source.get('mesh_sha256'):raise ValueError('Original mesh changed')
    record=source['runs'].get(name)
    if not record:raise ValueError('Requested response field is absent')
    if record['mode']!=(0 if name=='bare' else (1 if source.get('linear_material') else 2)):
        raise ValueError('Changed response-field material mode')
    job=work/name;field=job/'reaction.pos'
    receipt=json.loads((job/'solve.log.command.json').read_text())
    if receipt.get('status')!='completed' or receipt.get('exit_code')!=0:raise ValueError('Response solve did not complete')
    command=receipt.get('command',[])
    modes=[command[i+2] for i in range(len(command)-2) if command[i:i+2]==['-setnumber','Mode']]
    if modes!=[str(record['mode'])]:raise ValueError('Solver receipt does not match the reported physical material mode')
    if sha(field)!=record['reaction_field_sha256'] or sha(job/'project.pro')!=record['formulation_sha256']:
        raise ValueError('Original response field or formulation changed')
    certified_without_update=record.get('equilibrium_certificate',{}).get('iterations')==0
    if 'CONVERGED_' not in (job/'solve.log').read_text() and not certified_without_update:
        raise ValueError('Missing linear convergence evidence')
    if record['mode']==2:
        if 'equilibrium_certificate' in record:
            from getdp_equilibrium_check import certificate
            if certificate(job)!=record['equilibrium_certificate']:raise ValueError('Changed assembled-equilibrium certificate')
        elif getdp_nonlinear_convergence(job)!=record['nonlinear_convergence']:
            raise ValueError('Changed nonlinear convergence evidence')
    return field


def quadrature_levels(mover,stator=None):
    levels={'mover':mover,'stator':mover if stator is None else stator}
    if len(mover)<2 or any(len(values)!=len(mover) or
        any(type(n) is not int or not 0<=n<=6 for n in values) or
        any(a>=b for a,b in zip(values,values[1:])) for values in levels.values()):
        raise ValueError('Need matching-length increasing quadrature depth lists in [0,6] for both bodies')
    return levels


def force_level_checks(levels,depths):
    """Identical force gates for either independent field evaluator."""
    failures=[]
    for depth in depths:
        level=levels[str(depth)];level['action_reaction']={}
        for body in ['stator','mover']:
            keys=sorted(level['stack'][body])
            if set(level['bare'][body])!=set(keys):raise ValueError('Mismatched bare/material force paths')
            controls={name:{'stack_force_by_clearance_n':{c:level[name][body][c]['force_n'] for c in keys}} for name in ['bare','stack']}
            failures.extend(f'depth={depth} {body}: '+error for error in check_force_paths(controls))
        for c in sorted(level['stack']['stator']):
            check=action_reaction(level['stack']['stator'][c]['force_n'],level['stack']['mover'][c]['force_n'])
            level['action_reaction'][c]=check
            if not check['passed']:failures.append(f'depth={depth} path={c}: action/reaction failed')
    for a,b in zip(depths,depths[1:]):
        first=levels[str(a)];last=levels[str(b)];changes={}
        for body in ['stator','mover']:
            keys=sorted(last['stack'][body])
            reference=np.array([last['stack'][body][c]['force_n'] for c in keys])
            limits=np.maximum(1e-8,.02*np.linalg.norm(reference,axis=1))
            for name in ['bare','stack']:
                x=np.array([first[name][body][c]['force_n'] for c in keys]);y=np.array([last[name][body][c]['force_n'] for c in keys])
                error=np.linalg.norm(x-y,axis=1)
                changes[name+'/'+body]={'absolute_changes_n':error.tolist(),'limits_n':limits.tolist()}
                if np.any(error>limits):failures.append(f'{a}->{b} {name}/{body}: triangle quadrature failed')
        last['quadrature_changes']=changes
    return failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--depths',type=int,nargs='+',default=[1,2]);parser.add_argument('--remote-air-paths',action='store_true')
    parser.add_argument('--stator-depths',type=int,nargs='+',help='independent stator quadrature levels; same number as --depths, which then controls mover quadrature')
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('Preserve previous force audits')
    levels=quadrature_levels(args.depths,args.stator_depths)
    source=json.loads((work/'summary.json').read_text());fields={'bare':case_field(work,source,'bare')}
    if not source['bare_only']:fields['stack']=case_field(work,source,'stack')
    model=source['model'];quarter=source['quarter_symmetry']
    solver_model=validate_reduced_inputs(work,source)
    validate_mesh(work/'project.msh',solver_model,source['air_radius_m'])
    if quarter:validate_quarter_mesh(work/'project.msh')
    boxes={name:force_paths(model,name,args.remote_air_paths) for name in ['stator','mover']}
    for paths in boxes.values():
        for low,high in paths.values():
            if np.linalg.norm(np.maximum(abs(low),abs(high)))>=.95*source['air_radius_m']:
                raise ValueError('Force surface approaches the exterior boundary')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    snapshots=capture(args.output.parent,[Path(__file__),*[Path(__file__).parent/name for name in [
        'total_field_stress.py','cut_surface_force.py','read_vtu.py','reduced_potential.py','force_paths.py',
        'post_project_balance.py','post_project_force.py','project_static.py','project_symmetry.py','reduced_inputs.py']]])
    hashes={'summary':sha(work/'summary.json'),**{name:sha(path) for name,path in fields.items()}}
    report={'status':'running','scope':__doc__,'source_hashes':hashes,'source_snapshots':snapshots,
            'levels':{},'failures':[],'force_path_family':'remote-air' if args.remote_air_paths else 'near-interface',
            'quadrature_depths_by_body':levels,
            'force_gate':'max(10nN, 2%), unchanged; no failed floor subtraction'}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();incident=source_field(model)
    try:
        for name,path in fields.items():
            clear_vector_cache();stat=path.stat()
            vertices,response,*_=_vector_mesh(str(path.resolve()),stat.st_mtime_ns,stat.st_size,'response')
            if name=='bare':
                maximum=float(np.max(abs(response)))
                report['bare_response_maximum_t']=maximum
                if maximum>1e-12:raise ValueError('Nonzero FEM reaction in a uniform-vacuum algebraic control')
            if quarter:vertices,response=reflected_tetrahedra(vertices,response)
            for index,depth in enumerate(args.depths):
                level=report['levels'].setdefault(str(depth),{});level[name]={}
                for body,paths in boxes.items():
                    level[name][body]={}
                    for clearance,(low,high) in paths.items():
                        result=box_force(vertices,response,low,high,incident,levels[body][index])
                        level[name][body][clearance]=result
                        save()
                        print(name,depth,body,clearance,result['force_n'],flush=True)
                save()
            del vertices,response
        if 'stack' in fields:
            report['failures'].extend(force_level_checks(report['levels'],args.depths))
        if sha(work/'summary.json')!=hashes['summary'] or any(sha(path)!=hashes[name] for name,path in fields.items()):
            raise ValueError('Source fields changed during the force audit')
        for path,entry in snapshots.items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Force-audit implementation changed during validation')
        report['status']='failed' if report['failures'] else ('completed-bare-total-force-diagnostic-unqualified' if 'stack' not in fields else 'passed-total-field-surface-and-quadrature-only')
        save()
        if report['failures']:raise ValueError('\n'.join(report['failures']))
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
