#!/usr/bin/env python3
"""One-axis spatial or drive-length DC control on immutable physical copper.

Keeps the accepted numerical curvature setting fixed. A drive-length change
repartitions only the imposed unit-EMF region, never the physical copper union.
Global resistance checks alone do not qualify local currents or forces.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from audit_finite_dc_controls import MIXED,load,validate_control,resistance_check
from finite_copper_curvature import mesh_retained_cad,mesh_cad
from finite_copper_current import solve
from finite_copper_primal import saved_resistivity
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def refined_inputs(source,kind,value):
    if source['request']['geometry_order']!=1 or not source['request']['iterative']:
        raise ValueError('Completed linear-geometry iterative source required')
    if not np.isfinite(value) or value<=0:raise ValueError('Positive finite numerical control required')
    request=copy.deepcopy(source['request']);geometry=copy.deepcopy(source['geometry'])
    if kind=='mesh':
        if value>=request['mesh_m']:raise ValueError('Spatial mesh size must decrease')
        request['mesh_m']=value
    elif kind=='port':
        old=request['port_fraction']
        if value>=old or value>=1:raise ValueError('Drive-length fraction must decrease within the original straight port')
        points=np.asarray(geometry['drive_path_m']);centre=points.mean(axis=0);delta=(points[1]-points[0])*value/old
        geometry['drive_path_m']=[(centre-delta/2).tolist(),(centre+delta/2).tolist()]
        geometry['drive_volume_m3']*=value/old;request['port_fraction']=value
    else:raise ValueError('Unknown isolated DC refinement axis')
    return request,geometry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--kind',choices=['mesh','port'],required=True);parser.add_argument('--value',type=float,required=True)
    parser.add_argument('--max-dofs',type=int,default=24000000);parser.add_argument('--mesh-only',action='store_true')
    add_thread_option(parser);args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous numerical controls')
    if args.max_dofs<=0:parser.error('Positive pre-assembly resource cap required')
    source=load(origin,MIXED);request,geometry=refined_inputs(source,args.kind,args.value)
    curvature=source['request'].get('curvature_safety',2.)
    if curvature<=2:raise ValueError('This refinement path requires an explicit refined-curvature baseline')
    brep=next(Path(path) for path in source['input_hashes'] if path.endswith('/copper.brep'))
    physical=json.loads(brep.with_name('summary.json').read_text());rho=physical['geometry']['copper_resistivity_ohm_m']
    saved_resistivity(source,rho)
    import ngsolve as ng
    from netgen.occ import OCCGeometry
    if ng.__version__!=source['version']:raise ValueError('Refinement engine changed')
    work.mkdir(parents=True);started=time.monotonic();shutil.copy2(origin/'closed-copper.brep',work/'closed-copper.brep')
    bindings={str(path):sha(path) for path in [origin/'summary.json',origin/'mesh.vol',origin/'closed-copper.brep']}
    request.update(max_dofs=args.max_dofs,mesh_only=args.mesh_only)
    report=dict(status='running',scope=__doc__,version=ng.__version__,execution=runtime_metadata(),
        input_hashes=source['input_hashes'],geometry=geometry,request=request,brep_sha256=source['brep_sha256'],
        refinement_source=dict(work=str(origin),kind=args.kind,source_hashes=bindings),
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['finite_copper_curvature.py','finite_copper_current.py','finite_copper_circuit.py','finite_copper_primal.py','audit_finite_dc_controls.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    stages=[]
    def checkpoint(stage,**details):
        stages.append(dict(stage=stage,seconds=time.monotonic()-started,**details))
        (work/'meshing-progress.json').write_text(json.dumps(stages,indent=2,allow_nan=False)+'\n')
        print('refinement-stage',stage,round(stages[-1]['seconds'],3),flush=True)
    save()
    try:
        if args.kind=='mesh':
            numerical=copy.deepcopy(source);numerical['request']=request
            mesh,identity=mesh_retained_cad(ng,origin,numerical,curvature,checkpoint)
            report['retained_cad_input_reuse']=identity
        else:
            whole=OCCGeometry(str(work/'closed-copper.brep')).shape
            mesh=mesh_cad(ng,whole,geometry,request['mesh_m'],curvature,checkpoint)
        solids=list(mesh.ngmesh.GetGeometry().solids)
        drive=next(solid for solid in solids if solid.name=='drive')
        cad_error=abs(sum(solid.mass for solid in solids)/geometry['volume_m3']-1)
        drive_error=abs(drive.mass/geometry['drive_volume_m3']-1)
        if not np.isfinite([cad_error,drive_error]).all() or max(cad_error,drive_error)>1e-9:
            raise ValueError('Numerical drive partition changed physical CAD volume or prescribed port')
        mesh.ngmesh.Save(str(work/'mesh.vol'));mesh=ng.Mesh(str(work/'mesh.vol'))
        volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6));error=abs(volume/geometry['volume_m3']-1)
        report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,
            estimated_dofs=len(list(mesh.faces))+mesh.ne,materials=list(mesh.GetMaterials()),
            geometric_volume_check=dict(mesh_volume_m3=volume,exact_cad_volume_m3=geometry['volume_m3'],relative_difference=error,limit=.02),
            cad_partition_checks=dict(physical_union_relative_error=cad_error,drive_volume_relative_error=drive_error))
        save()
        if error>.02:raise ValueError('Refinement mesh misses unchanged2%CAD volume gate')
        if report['estimated_dofs']>args.max_dofs:raise ValueError('DC refinement resource cap exceeded before assembly')
        if not args.mesh_only:
            port=np.asarray(geometry['drive_path_m']);delta=port[1]-port[0]
            electric=mesh.MaterialCF({'drive':ng.CoefficientFunction(tuple(delta/np.dot(delta,delta)))},default=ng.CoefficientFunction((0.,0.,0.)))
            solution,dc=solve(ng,mesh,electric,rho,True,work/'linear-progress.json','amg')
            solution.Save(str(work/'dc-current-potential.sol'))
            report.update(solution_sha256=sha(work/'dc-current-potential.sol'),
                dc=dict(dc,drive_emf_v=1.,effective_loop_current_a=dc['source_power_w'],effective_loop_resistance_ohm=1/dc['source_power_w']))
            validate_control(source,report|{'status':MIXED},args.kind)
            report['resistance_refinement_check']=resistance_check(source,report,.02)
            if not report['resistance_refinement_check']['passed']:raise ValueError('Isolated DC resistance refinement fails unchanged2%gate')
        for path,digest in (source['input_hashes']|bindings).items():
            if sha(Path(path))!=digest:raise ValueError('Numerical refinement inputs changed')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Numerical refinement implementation changed')
        report.update(status='completed-isolated-dc-refinement-mesh-only' if args.mesh_only else MIXED,seconds=time.monotonic()-started);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
