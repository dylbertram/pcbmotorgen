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


def generate_mesh(ng,domain,maxh,curvature):
    if not np.isfinite([maxh,curvature]).all() or maxh<=0 or curvature<=2:
        raise ValueError('Need positive size and a declared curvature refinement above default2')
    from netgen.occ import OCCGeometry
    domain.maxh=maxh
    mesh=ng.Mesh(OCCGeometry(domain).GenerateMesh(maxh=maxh,curvaturesafety=curvature));mesh.Curve(1)
    return mesh


def mesh_cad(ng,whole,geometry,maxh,curvature):
    from netgen.occ import Glue
    start,end=np.asarray(geometry['drive_path_m'])
    drive=whole*return_prism(start,end,geometry['return_width_m'],geometry['return_thickness_m'])
    rest=whole-drive;drive.mat('drive');rest.mat('copper');domain=Glue([rest,drive])
    return generate_mesh(ng,domain,maxh,curvature)


def validate_mesh_reuse(prior,source,curvature):
    if prior.get('status')!='failed' or prior.get('error')!='Curvature DC resource cap exceeded before assembly':
        raise ValueError('Only a completed pre-assembly resource-cap mesh may be reused')
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
    parser.add_argument('--pressure-solver',choices=['factor','amg'],default='factor')
    add_thread_option(parser);args=parser.parse_args()
    origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous curvature controls')
    if args.max_dofs<1:parser.error('Positive resource cap required')
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
        'request':dict(source['request'],curvature_safety=args.curvature_safety,max_dofs=args.max_dofs,pressure_solver=args.pressure_solver),
        'curvature_control_source':{'work':str(origin),'summary_sha256':sha(origin/'summary.json'),'default_curvature_safety':2.},
        'source_snapshots':capture(work,[Path(__file__),*[Path(__file__).with_name(p) for p in
            ['audit_finite_dc_controls.py','finite_copper_circuit.py','finite_copper_current.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        if args.mesh_work:
            mesh_work=args.mesh_work.resolve();prior=json.loads((mesh_work/'summary.json').read_text())
            validate_mesh_reuse(prior,source,args.curvature_safety)
            receipt=json.loads(Path(prior['command_receipt']).read_text())
            if receipt.get('status')!='failed' or receipt.get('exit_code')==0:
                raise ValueError('Reused curvature mesh has no finished failure receipt')
            if (mesh_work/'dc-current-potential.sol').exists() or (mesh_work/'unaccepted-current-potential.sol').exists():
                raise ValueError('Curvature input reuse must not import a failed field')
            if sha(mesh_work/'mesh.vol')!=prior['mesh_sha256'] or sha(mesh_work/'closed-copper.brep')!=source['brep_sha256']:
                raise ValueError('Reused curvature geometry/mesh changed')
            shutil.copy2(mesh_work/'mesh.vol',work/'mesh.vol')
            if sha(work/'mesh.vol')!=prior['mesh_sha256']:raise ValueError('Curvature mesh changed during copy')
            mesh=ng.Mesh(str(work/'mesh.vol'))
            report['mesh_input_reuse']={'work':str(mesh_work),'summary_sha256':sha(mesh_work/'summary.json'),
                'scope':'Verified CAD/mesh only from pre-assembly resource-cap failure. No solution imported; all DC equations and gates rerun.'}
        else:
            whole=OCCGeometry(str(work/'closed-copper.brep')).shape
            mesh=mesh_cad(ng,whole,source['geometry'],source['request']['mesh_m'],args.curvature_safety)
        mesh.ngmesh.Save(str(work/'mesh.vol'));volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6))
        error=abs(volume/source['geometry']['volume_m3']-1)
        report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,materials=list(mesh.GetMaterials()),
            estimated_dofs=len(list(mesh.faces))+mesh.ne,
            geometric_volume_check={'mesh_volume_m3':volume,'exact_cad_volume_m3':source['geometry']['volume_m3'],'relative_difference':error,'limit':.02})
        save()
        if error>.02:raise ValueError('Finite copper mesh misses exact-CAD volume gate')
        if report['estimated_dofs']>args.max_dofs:raise ValueError('Curvature DC resource cap exceeded before assembly')
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
