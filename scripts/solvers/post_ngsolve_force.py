#!/usr/bin/env python3
"""Apply the unchanged force gates to an independent high-order total field.

NGSolve gradients are evaluated directly at triangle quadrature points, not
projected onto affine nodal fields. The prescribed-source stress is included.
The vacuum control is checked in the independent FE space before integration.
"""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np

from cut_surface_force import reflected_tetrahedra
from force_paths import force_paths
from ngsolve_reduced import load_solution, total_field, energy_form
from post_project_force import sha
from post_reduced_force import case_field, quadrature_levels, force_level_checks
from project_static import validate_mesh
from project_symmetry import validate_quarter_mesh
from read_vtu import _vector_mesh
from reduced_inputs import validate_reduced_inputs
from reduced_potential import source_field, MU0
from source_snapshot import capture
from total_field_stress import box_force
from force_checkpoint import compatible_checkpoint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--depths',type=int,nargs='+',default=[3,4]);parser.add_argument('--stator-depths',type=int,nargs='+',default=[0,1])
    parser.add_argument('--remote-air-paths',action='store_true')
    parser.add_argument('--reuse-report',type=Path,help='interrupted postprocessing cache; source fields must already be complete')
    parser.add_argument('--reuse-receipt',type=Path,help='authoritative interrupted supervisor receipt for --reuse-report')
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('Preserve previous independent force audits')
    if bool(args.reuse_report)!=bool(args.reuse_receipt):parser.error('Checkpoint report and receipt must be supplied together')
    levels=quadrature_levels(args.depths,args.stator_depths)
    ng,independent,mesh,fes,solution=load_solution(work)
    receipt=json.loads(Path(independent['command_receipt']).read_text());command=receipt['command']
    origin=Path(command[command.index('--source-work')+1])
    if sha(origin/'summary.json')!=independent['source_summary_sha256']:raise ValueError('Original physical input report changed')
    original=json.loads((origin/'summary.json').read_text());solver=validate_reduced_inputs(origin,original)
    if independent['model']!=original['model'] or independent['solver_geometry_model']!=solver:
        raise ValueError('Independent physical source/material metadata changed')
    if independent['linear_material']!=('--linear' in command):raise ValueError('Independent material mode differs from the command receipt')
    if sha(work/'project.msh')!=sha(origin/'project.msh'):raise ValueError('Independent/source physical meshes differ')
    validate_mesh(work/'project.msh',solver,independent['air_radius_m'])
    if independent['quarter_symmetry']:validate_quarter_mesh(work/'project.msh')
    field=case_field(origin,original,'bare');stat=field.stat()
    vertices,zero,*_=_vector_mesh(str(field.resolve()),stat.st_mtime_ns,stat.st_size,'response')
    if np.max(abs(zero))>1e-12:raise ValueError('Original zero-field geometry export is not a vacuum response')
    vacuum=ng.GridFunction(fes,name='vacuum')
    vacuum_model=copy.deepcopy(solver)
    for material in vacuum_model['stack']:material.update(mu_r=1.,bsat_t=None)
    vacuum_form,_=energy_form(ng,mesh,fes,independent['model'],vacuum_model,True,independent['bonus_integration_order'])
    residual=vacuum.vec.CreateVector();vacuum_form.Apply(vacuum.vec,residual)
    free=np.array(fes.FreeDofs(),dtype=bool);vacuum_residual=float(np.linalg.norm(residual.FV().NumPy()[free]))
    if vacuum_residual>1e-12:raise ValueError('Independent vacuum algebraic control failed')
    if independent['quarter_symmetry']:vertices,zero=reflected_tetrahedra(vertices,zero)
    _,total=total_field(work);incident=source_field(independent['model'])
    boxes={name:force_paths(independent['model'],name,args.remote_air_paths) for name in ['stator','mover']}
    for paths in boxes.values():
        for low,high in paths.values():
            if np.linalg.norm(np.maximum(abs(low),abs(high)))>=.95*independent['air_radius_m']:
                raise ValueError('Independent force surface approaches the exterior boundary')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    snapshots=capture(args.output.parent,[Path(__file__),*[Path(__file__).parent/name for name in [
        'ngsolve_reduced.py','total_field_stress.py','cut_surface_force.py','post_reduced_force.py','reduced_inputs.py',
        'reduced_potential.py','force_paths.py','post_project_balance.py','read_vtu.py','force_checkpoint.py']]])
    hashes={'summary':sha(work/'summary.json'),'solution':sha(work/'psi.sol'),'mesh':sha(work/'project.msh')}
    report={'status':'running','scope':__doc__,'source_hashes':hashes,'source_snapshots':snapshots,'levels':{},'failures':[],
        'backend':'NGSolve','basis_order':independent['order'],'quadrature_depths_by_body':levels,
        'vacuum_residual_norm':vacuum_residual,'force_path_family':'remote-air' if args.remote_air_paths else 'near-interface',
        'field_evaluation':'Exact high-order FE gradient plus analytical source at quadrature points; no affine projection, field scaling or floor subtraction'}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    if args.reuse_report:
        physics={name:Path(__file__).parent/name for name in ['ngsolve_reduced.py','total_field_stress.py','cut_surface_force.py',
            'reduced_potential.py','force_paths.py','post_project_balance.py','read_vtu.py']}
        report['levels']=compatible_checkpoint(args.reuse_report,args.reuse_receipt,report,physics,boxes)
        report['reused_checkpoint_sha256']=sha(args.reuse_report)
        report['reused_checkpoint_receipt_sha256']=sha(args.reuse_receipt)
        report['checkpoint_scope']='Reused quadrature units only; the original interrupted audit remains unaccepted. All gates rerun in this new job.'
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for index,depth in enumerate(args.depths):
            level=report['levels'].setdefault(str(depth),{})
            for name,evaluate in [('bare',incident),('stack',total)]:
                case=level.setdefault(name,{})
                for body,paths in boxes.items():
                    surfaces=case.setdefault(body,{})
                    for clearance,(low,high) in paths.items():
                        if clearance in surfaces:
                            print('reused',name,depth,body,clearance,flush=True)
                            continue
                        # The zero affine component is intentional: the FULL
                        # high-order field is evaluated by the callback, rather
                        # than approximating its gradient by vertex interpolation.
                        result=box_force(vertices,zero,low,high,evaluate,levels[body][index])
                        surfaces[clearance]=result
                        save()
                        print(name,depth,body,clearance,result['force_n'],flush=True)
                save()
        report['failures']=force_level_checks(report['levels'],args.depths)
        if any(sha(work/path)!=hashes[key] for key,path in [('summary','summary.json'),('solution','psi.sol'),('mesh','project.msh')]):
            raise ValueError('Independent physical fields changed during audit')
        for path,entry in snapshots.items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Independent audit implementation changed')
        if args.reuse_report and (sha(args.reuse_report)!=report['reused_checkpoint_sha256'] or sha(args.reuse_receipt)!=report['reused_checkpoint_receipt_sha256']):
            raise ValueError('Original interrupted checkpoint changed during the new audit')
        report['status']='failed' if report['failures'] else 'passed-independent-total-field-surface-and-quadrature-only'
        save()
        if report['failures']:raise ValueError('\n'.join(report['failures']))
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
