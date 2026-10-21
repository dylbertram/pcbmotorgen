#!/usr/bin/env python3
"""Isolated curvature refinement of immutable saved-copper CAD and DC physics.

Global maxh refinement alone can leave circular barrel tessellation unchanged.
This study changes Netgen's curvature safety, not copper radii, plating, depths,
drive port, resistivity, solver tolerance or acceptance gates.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from audit_finite_dc_controls import MIXED,load,resistance_check
from finite_copper_circuit import return_prism
from finite_copper_current import solve
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def generate_mesh(ng,domain,maxh,curvature,checkpoint=None):
    if not np.isfinite([maxh,curvature]).all() or maxh<=0 or curvature<=2:
        raise ValueError('Need positive size and a declared curvature refinement above default2')
    from netgen.occ import OCCGeometry
    domain.maxh=maxh
    if checkpoint:checkpoint('native-mesh-generation-start')
    mesh=ng.Mesh(OCCGeometry(domain).GenerateMesh(maxh=maxh,curvaturesafety=curvature));mesh.Curve(1)
    if checkpoint:checkpoint('native-mesh-generation-complete',elements=mesh.ne,vertices=mesh.nv)
    return mesh


def mesh_cad(ng,whole,geometry,maxh,curvature,checkpoint=None):
    from netgen.occ import Glue
    start,end=np.asarray(geometry['drive_path_m'])
    if checkpoint:checkpoint('drive-cad-intersection-start')
    drive=whole*return_prism(start,end,geometry['return_width_m'],geometry['return_thickness_m'])
    if checkpoint:checkpoint('drive-cad-intersection-complete',drive_volume_m3=float(drive.mass))
    if checkpoint:checkpoint('remaining-copper-cad-subtraction-start')
    rest=whole-drive;drive.mat('drive');rest.mat('copper')
    if checkpoint:checkpoint('remaining-copper-cad-subtraction-complete')
    domain=Glue([rest,drive])
    if checkpoint:checkpoint('cad-domain-glued')
    return generate_mesh(ng,domain,maxh,curvature,checkpoint)


def mesh_retained_cad(ng,origin,source,curvature,checkpoint=None):
    """Fresh tessellation of CAD retained in the exact original source mesh.

    Never infer geometry identity from counts or reserialized mesh bytes, and
    never load/reuse a prior current field. Preserves the original drive split.
    """
    if not np.isfinite(curvature) or curvature<=2:raise ValueError('Declared curvature refinement above default2 required')
    path=Path(origin)/'mesh.vol'
    if sha(path)!=source['mesh_sha256']:raise ValueError('Retained CAD requires the exact immutable original mesh bytes')
    if source['version']!=ng.__version__:raise ValueError('Retained CAD engine changed')
    if checkpoint:checkpoint('retained-source-cad-load-start')
    original=ng.Mesh(str(path));geometry=original.ngmesh.GetGeometry()
    if geometry is None or not hasattr(geometry,'shape'):raise ValueError('Original mesh does not retain OCC CAD; no fallback geometry substitution')
    solids=list(geometry.solids)
    if sorted(solid.name for solid in solids)!=['copper','drive']:
        raise ValueError('Retained CAD does not preserve the original copper/drive material partition')
    volume=float(sum(solid.mass for solid in solids));drive=next(solid for solid in solids if solid.name=='drive')
    relative=abs(volume/source['geometry']['volume_m3']-1)
    drive_relative=abs(float(drive.mass)/source['geometry']['drive_volume_m3']-1)
    expected=np.asarray(source['geometry']['drive_path_m']).mean(axis=0)
    centre_error=float(np.linalg.norm(np.asarray(tuple(drive.center))-expected))
    if not np.isfinite([relative,drive_relative,centre_error]).all() or relative>1e-9 or drive_relative>1e-9 or centre_error>1e-12:
        raise ValueError('Retained CAD volume/drive identity check failed')
    if sha(path)!=source['mesh_sha256']:raise ValueError('Original mesh changed while retained CAD loaded')
    identity=dict(source_mesh_sha256=source['mesh_sha256'],cad_volume_relative_reload_error=relative,
        drive_volume_relative_reload_error=drive_relative,drive_centre_error_m=centre_error,
        scope='Only CAD retained in exact verified original mesh bytes. Fresh mesh and DC solve; no previous field or count-based identity.')
    if checkpoint:checkpoint('retained-cad-identity-verified',**identity)
    geometry.shape.maxh=source['request']['mesh_m']
    if checkpoint:checkpoint('native-mesh-generation-start')
    mesh=ng.Mesh(geometry.GenerateMesh(maxh=source['request']['mesh_m'],curvaturesafety=curvature));mesh.Curve(1)
    if checkpoint:checkpoint('native-mesh-generation-complete',elements=mesh.ne,vertices=mesh.nv)
    return mesh,identity


def validate_mesh_reuse(prior,source,curvature):
    checkpoint=prior.get('status')=='completed-finite-copper-curvature-mesh-only'
    capped=prior.get('status')=='failed' and prior.get('error')=='Curvature DC resource cap exceeded before assembly'
    if not checkpoint and not capped:
        raise ValueError('Only a completed mesh-only or pre-assembly resource-cap mesh may be reused')
    for key in ['version','input_hashes','geometry','brep_sha256']:
        if prior[key]!=source[key]:raise ValueError('Reused curvature mesh has different saved physical inputs')
    for key in ['mesh_m','port_fraction','geometry_order','iterative']:
        if prior['request'][key]!=source['request'][key]:raise ValueError('Reused curvature mesh changed controls')
    if prior['request']['curvature_safety']!=curvature:raise ValueError('Reused mesh has different curvature safety')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--curvature-safety',type=float,default=4.)
    parser.add_argument('--max-dofs',type=int,default=3500000)
    parser.add_argument('--mesh-work',type=Path,help='reuse only hashed inputs from a pre-assembly curvature resource-cap failure')
    parser.add_argument('--reuse-cad-from-source-mesh',action='store_true',help='Reuse only exact original source mesh embedded CAD/drive partition; generate a new mesh and solve')
    parser.add_argument('--mesh-only',action='store_true',help='Save/validate refined mesh as an input checkpoint; do not assemble a DC system')
    parser.add_argument('--pressure-solver',choices=['factor','amg'],default='factor')
    add_thread_option(parser);args=parser.parse_args()
    origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous curvature controls')
    if args.max_dofs<1:parser.error('Positive resource cap required')
    if args.mesh_work and args.reuse_cad_from_source_mesh:parser.error('Choose one explicit geometry/mesh input reuse path')
    source=load(origin,MIXED)
    if source['request']['geometry_order']!=1 or not source['request']['iterative']:
        raise ValueError('Need completed linear-geometry block-DC source')
    if source['request'].get('curvature_safety',2.)!=2.:
        raise ValueError('This isolated control compares against default curvature safety2')
    import ngsolve as ng
    from netgen.occ import OCCGeometry
    if ng.__version__!=source['version']:raise ValueError('Curvature control engine changed')
    brep=next(Path(p) for p in source['input_hashes'] if p.endswith('/copper.brep'))
    geometry_path=brep.with_name('summary.json');geometry=json.loads(geometry_path.read_text())
    work.mkdir(parents=True);started=time.monotonic();shutil.copy2(origin/'closed-copper.brep',work/'closed-copper.brep')
    report={'status':'running','scope':__doc__,'version':ng.__version__,'execution':runtime_metadata(),
        'input_hashes':source['input_hashes'],'geometry':source['geometry'],'brep_sha256':source['brep_sha256'],
        'request':dict(source['request'],curvature_safety=args.curvature_safety,max_dofs=args.max_dofs,pressure_solver=args.pressure_solver,
                       retained_source_cad=args.reuse_cad_from_source_mesh,mesh_only=args.mesh_only),
        'curvature_control_source':{'work':str(origin),'summary_sha256':sha(origin/'summary.json'),'default_curvature_safety':2.},
        'source_snapshots':capture(work,[Path(__file__),*[Path(__file__).with_name(p) for p in
            ['audit_finite_dc_controls.py','finite_copper_circuit.py','finite_copper_current.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    stages=[]
    def checkpoint(stage,**details):
        stages.append(dict(stage=stage,seconds=time.monotonic()-started,**details))
        (work/'meshing-progress.json').write_text(json.dumps(stages,indent=2,allow_nan=False)+'\n')
        print('curvature-stage',stage,round(stages[-1]['seconds'],3),flush=True)
    save()
    try:
        if args.mesh_work:
            mesh_work=args.mesh_work.resolve();prior=json.loads((mesh_work/'summary.json').read_text())
            validate_mesh_reuse(prior,source,args.curvature_safety)
            receipt=json.loads(Path(prior['command_receipt']).read_text())
            expected_status='completed' if prior['status']=='completed-finite-copper-curvature-mesh-only' else 'failed'
            if receipt.get('status')!=expected_status or (expected_status=='completed' and receipt.get('exit_code')!=0) or (expected_status=='failed' and receipt.get('exit_code')==0):
                raise ValueError('Reused curvature mesh has no matching finished receipt')
            if (mesh_work/'dc-current-potential.sol').exists() or (mesh_work/'unaccepted-current-potential.sol').exists():
                raise ValueError('Curvature input reuse must not import a failed field')
            if sha(mesh_work/'mesh.vol')!=prior['mesh_sha256'] or sha(mesh_work/'closed-copper.brep')!=source['brep_sha256']:
                raise ValueError('Reused curvature geometry/mesh changed')
            shutil.copy2(mesh_work/'mesh.vol',work/'mesh.vol')
            if sha(work/'mesh.vol')!=prior['mesh_sha256']:raise ValueError('Curvature mesh changed during copy')
            mesh=ng.Mesh(str(work/'mesh.vol'))
            report['mesh_input_reuse']={'work':str(mesh_work),'summary_sha256':sha(mesh_work/'summary.json'),
                'scope':'Verified CAD/mesh only from pre-assembly resource-cap failure. No solution imported; all DC equations and gates rerun.'}
        elif args.reuse_cad_from_source_mesh:
            mesh,identity=mesh_retained_cad(ng,origin,source,args.curvature_safety,checkpoint)
            report['retained_cad_input_reuse']=identity
        else:
            whole=OCCGeometry(str(work/'closed-copper.brep')).shape
            mesh=mesh_cad(ng,whole,source['geometry'],source['request']['mesh_m'],args.curvature_safety,checkpoint)
        if not args.mesh_work:mesh.ngmesh.Save(str(work/'mesh.vol'))
        # Consume the exact saved bytes, not an assumed-equivalent reserialization
        # or element-count identity. Never resave a reused mesh under a new hash.
        mesh=ng.Mesh(str(work/'mesh.vol'))
        volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6))
        error=abs(volume/source['geometry']['volume_m3']-1)
        report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,materials=list(mesh.GetMaterials()),
            estimated_dofs=len(list(mesh.faces))+mesh.ne,
            geometric_volume_check={'mesh_volume_m3':volume,'exact_cad_volume_m3':source['geometry']['volume_m3'],'relative_difference':error,'limit':.02})
        save()
        if error>.02:raise ValueError('Finite copper mesh misses exact-CAD volume gate')
        if report['estimated_dofs']>args.max_dofs:raise ValueError('Curvature DC resource cap exceeded before assembly')
        if args.mesh_only:
            for name,digest in report['input_hashes'].items():
                if sha(Path(name))!=digest:raise ValueError('Curvature mesh physical input changed')
            for name,entry in report['source_snapshots'].items():
                if sha(Path(name))!=entry['sha256']:raise ValueError('Curvature mesh implementation changed')
            report.update(status='completed-finite-copper-curvature-mesh-only',seconds=time.monotonic()-started);save();return
        port=np.asarray(source['geometry']['drive_path_m']);delta=port[1]-port[0]
        electric=mesh.MaterialCF({'drive':ng.CoefficientFunction(tuple(delta/np.dot(delta,delta)))},default=ng.CoefficientFunction((0,0,0)))
        solution,dc=solve(ng,mesh,electric,geometry['geometry']['copper_resistivity_ohm_m'],True,work/'linear-progress.json',args.pressure_solver)
        solution.Save(str(work/'dc-current-potential.sol'));report['solution_sha256']=sha(work/'dc-current-potential.sol')
        report['dc']=dict(dc,drive_emf_v=1.,effective_loop_current_a=dc['source_power_w'],effective_loop_resistance_ohm=1/dc['source_power_w'])
        report['resistance_curvature_check']=resistance_check(source,report,.02)
        # Local barrel sections must be audited separately, even if R is stable.
        for name,digest in report['input_hashes'].items():
            if sha(Path(name))!=digest:raise ValueError('Curvature control physical input changed')
        for name,entry in report['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Curvature control implementation changed')
        report.update(status=MIXED,seconds=time.monotonic()-started);save()
        if not report['resistance_curvature_check']['passed']:
            raise ValueError('Curvature resistance refinement failed')
    except BaseException as error:
        if hasattr(error,'details'):report['linear_failure']=error.details
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
