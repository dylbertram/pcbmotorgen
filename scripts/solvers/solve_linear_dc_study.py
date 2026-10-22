#!/usr/bin/env python3
"""Fresh mixed DC basis for actual prepared linear copper, with explicit curvature.

Reuses exact physical CAD only. No archived field, fixture substitution or force
admission. Numerical controls must match the separately declared case matrix.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_copper_circuit import drive_segment
from finite_copper_curvature import mesh_cad
from finite_copper_current import solve
from post_project_force import sha
from prepare_linear_dc_copper import validate_copper_shape
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def validate_controls(matrix,study,mesh,curvature,port,max_dofs):
    if matrix.get('schema')!='declared-linear-dc-acceptance-matrix-v1':raise ValueError('Declared acceptance matrix required')
    controls=matrix['source_controls']
    if mesh not in controls['mesh_m'] or curvature not in controls['curvature_safety'] or port not in controls['port_fraction']:
        raise ValueError('Source controls must match the declared acceptance matrix')
    if type(max_dofs) is not int or not 0<max_dofs<=24000000:raise ValueError('Positive source DOF cap no greater than24M required')
    if study['status']!='prepared-actual-linear-study-no-source-or-force-acceptance':raise ValueError('Actual prepared study required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-work',type=Path,required=True);parser.add_argument('--matrix',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--mesh',type=float,required=True)
    parser.add_argument('--curvature-safety',type=float,required=True);parser.add_argument('--port-fraction',type=float,required=True)
    parser.add_argument('--max-dofs',type=int,required=True);parser.add_argument('--mesh-only',action='store_true')
    add_thread_option(parser);args=parser.parse_args();origin=args.geometry_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous source trials')
    physical=json.loads((origin/'summary.json').read_text());returned=json.loads((origin/'return/summary.json').read_text())
    completed_receipt(physical);completed_receipt(returned)
    if physical['status']!='completed-finite-copper-geometry-only-unqualified' or returned['status']!='prepared-physical-dc-return-geometry-only' or returned['failures']:
        raise ValueError('Completed exact copper and explicit return required')
    study_path=Path(physical['actual_study_work'])/'summary.json';study=json.loads(study_path.read_text())
    matrix=json.loads(args.matrix.read_text());validate_controls(matrix,study,args.mesh,args.curvature_safety,args.port_fraction,args.max_dofs)
    declaration=(Path(__file__).resolve().parents[2]/matrix['study_inputs']).resolve()
    if study['input_hashes'].get(str(declaration))!=sha(declaration):raise ValueError('Matrix and prepared study have different declared physical inputs')
    if physical['translation_m']!=returned['translation_m'] or physical['input_hashes']!=returned['input_hashes']:
        raise ValueError('Copper and return physical provenance differs')
    for name,digest in (physical['input_hashes']|study['input_hashes']).items():
        if sha(Path(name))!=digest:raise ValueError('Actual source physical input changed')
    for name,key in [('copper.brep','brep_sha256'),('closed-copper-for-partition-audit.brep','closed_partition_brep_sha256')]:
        if sha(origin/name)!=physical[key]:raise ValueError('Exact physical CAD changed')
    import ngsolve as ng
    from netgen.occ import OCCGeometry
    work.mkdir(parents=True);started=time.monotonic()
    # Keep the established three-input contract for downstream section/primal auditors.
    inputs={str(p):sha(p) for p in [origin/'summary.json',origin/'copper.brep',origin/'return/summary.json']}
    bindings={str(p):sha(p) for p in [args.matrix.resolve(),study_path,origin/'closed-copper-for-partition-audit.brep']}
    report=dict(status='running',scope=__doc__,version=ng.__version__,execution=runtime_metadata(),input_hashes=inputs,
        study_bindings=bindings,request=dict(mesh_m=args.mesh,curvature_safety=args.curvature_safety,port_fraction=args.port_fraction,
            geometry_order=1,iterative=True,pressure_solver='amg',max_dofs=args.max_dofs,mesh_only=args.mesh_only),
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['finite_copper_circuit.py','finite_copper_curvature.py','finite_copper_current.py','prepare_linear_dc_copper.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    stages=[]
    def checkpoint(stage,**details):
        stages.append(dict(stage=stage,seconds=time.monotonic()-started,**details))
        (work/'meshing-progress.json').write_text(json.dumps(stages,indent=2,allow_nan=False)+'\n')
        print('linear-study-stage',stage,round(stages[-1]['seconds'],3),flush=True)
    save()
    try:
        shutil.copy2(origin/'closed-copper-for-partition-audit.brep',work/'closed-copper.brep')
        if sha(work/'closed-copper.brep')!=physical['closed_partition_brep_sha256']:raise ValueError('Closed CAD changed while copied')
        # Independently reject empty/return-only CAD even if an older preparer
        # omitted the nonempty-union guard. No regeneration or healing.
        validate_copper_shape(OCCGeometry(str(origin/'copper.brep')).shape)
        whole=OCCGeometry(str(work/'closed-copper.brep')).shape;validate_copper_shape(whole)
        layer=physical['geometry']['layers'][0];points=np.asarray(returned['closure']['return_path_m'])
        start,end=drive_segment(points,layer['trace_width_m'],args.port_fraction)
        geometry=dict(volume_m3=physical['closed_partition_volume_m3'],solid_components=len(whole.solids),return_path_m=points.tolist(),
            return_width_m=layer['trace_width_m'],return_thickness_m=layer['thickness_m'],drive_path_m=[start.tolist(),end.tolist()],
            drive_volume_m3=float(np.linalg.norm(end-start)*layer['trace_width_m']*layer['thickness_m']))
        if len(whole.solids)!=1:raise ValueError('Closed current CAD is not one connected conductor')
        report.update(geometry=geometry,brep_sha256=sha(work/'closed-copper.brep'));save()
        mesh=mesh_cad(ng,whole,geometry,args.mesh,args.curvature_safety,checkpoint)
        solids=list(mesh.ngmesh.GetGeometry().solids);drive=next(solid for solid in solids if solid.name=='drive')
        errors=[abs(sum(solid.mass for solid in solids)/geometry['volume_m3']-1),abs(drive.mass/geometry['drive_volume_m3']-1)]
        if not np.isfinite(errors).all() or max(errors)>1e-9:raise ValueError('Drive partition changed physical CAD or declared drive volume')
        mesh.ngmesh.Save(str(work/'mesh.vol'));mesh=ng.Mesh(str(work/'mesh.vol'))
        volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6));error=abs(volume/geometry['volume_m3']-1)
        report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,materials=list(mesh.GetMaterials()),
            estimated_dofs=len(list(mesh.faces))+mesh.ne,cad_partition_checks=dict(physical_union_relative_error=errors[0],drive_volume_relative_error=errors[1]),
            geometric_volume_check=dict(mesh_volume_m3=volume,exact_cad_volume_m3=geometry['volume_m3'],relative_difference=error,limit=.02));save()
        if not np.isfinite(error) or error>.02:raise ValueError('Source mesh misses unchanged2%CAD volume gate')
        if report['estimated_dofs']>args.max_dofs:raise ValueError('Source resource cap exceeded before assembly')
        if not args.mesh_only:
            delta=end-start;electric=mesh.MaterialCF({'drive':ng.CoefficientFunction(tuple(delta/np.dot(delta,delta)))},default=ng.CoefficientFunction((0.,0.,0.)))
            solution,dc=solve(ng,mesh,electric,physical['geometry']['copper_resistivity_ohm_m'],True,work/'linear-progress.json','amg')
            solution.Save(str(work/'dc-current-potential.sol'));report.update(solution_sha256=sha(work/'dc-current-potential.sol'),
                dc=dict(dc,drive_emf_v=1.,effective_loop_current_a=dc['source_power_w'],effective_loop_resistance_ohm=1/dc['source_power_w']))
        for name,digest in (inputs|bindings|physical['input_hashes']|study['input_hashes']).items():
            if sha(Path(name))!=digest:raise ValueError('Source physical input or declaration changed')
        for name,entry in report['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Source implementation changed')
        report.update(status='completed-linear-study-mesh-only' if args.mesh_only else 'completed-finite-copper-closed-dc-basis-unqualified',seconds=time.monotonic()-started);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
