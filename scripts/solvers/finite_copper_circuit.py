#!/usr/bin/env python3
"""Mesh a finite saved-copper circuit and solve a closed DC current basis.

Saved traces/pads/barrels are unchanged. External return is the previously
archived explicit screening route, using saved outer copper cross-section.
This is DC source preparation only, not magnetic/self-inductance qualification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_copper_geometry import fuse_all
from finite_copper_current import solve
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def return_prism(a,b,width,thickness):
    from netgen.occ import Pnt,Vec,Segment,Wire,Face
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float);delta=b-a;length=np.linalg.norm(delta)
    if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite([a,b]).all() or length<=0 or min(width,thickness)<=0:
        raise ValueError('Invalid finite return segment')
    direction=delta/length;normal=np.cross(direction,[0.,0.,1.])
    if np.linalg.norm(normal)<1e-12:normal=np.array([1.,0.,0.])
    else:normal/=np.linalg.norm(normal)
    vertical=np.cross(direction,normal)
    corners=[a+s*width/2*normal+t*thickness/2*vertical for s,t in [(1,1),(-1,1),(-1,-1),(1,-1)]]
    return Face(Wire([Segment(Pnt(*corners[i]),Pnt(*corners[(i+1)%4])) for i in range(4)])).Extrude(Vec(*delta))


def drive_segment(points,width,fraction):
    points=np.asarray(points,dtype=float);delta=points[2]-points[1];length=np.linalg.norm(delta)
    if not 0<fraction<=1 or length<=0:raise ValueError('Invalid DC drive-port fraction')
    margin=(1-fraction)*length/2
    if margin<=width/2:raise ValueError('Drive port must avoid widened return-bend junctions')
    direction=delta/length
    return points[1]+margin*direction,points[2]-margin*direction


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-work',type=Path,required=True);parser.add_argument('--return-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--mesh',type=float,default=.0002)
    parser.add_argument('--max-dofs',type=int,default=800000);parser.add_argument('--geometry-only',action='store_true');parser.add_argument('--mesh-only',action='store_true')
    parser.add_argument('--iterative',action='store_true',help='original mixed equations with bounded block MINRES instead of full LU')
    parser.add_argument('--pressure-solver',choices=['factor','amg'],default='factor',help='linear preconditioner only; amg requires separate pinned PyAMG5.3.0')
    parser.add_argument('--mesh-work',type=Path,help='reuse hash-verified geometry/mesh inputs only; never accepts a prior failed DC solution')
    parser.add_argument('--port-fraction',type=float,default=.5,help='central straight-branch drive fraction, clear of bend current paths')
    parser.add_argument('--geometry-order',type=int,choices=[1,2],default=1,help='declared geometric discretization; validate against exact saved copper CAD')
    add_thread_option(parser);args=parser.parse_args();work=args.work.resolve();geometry_work=args.geometry_work.resolve();return_work=args.return_work.resolve()
    if work.exists():parser.error('Preserve previous finite circuit trials')
    if not np.isfinite(args.mesh) or args.mesh<=0 or args.max_dofs<1:parser.error('Invalid mesh/resource controls')
    geometry=json.loads((geometry_work/'summary.json').read_text());source=json.loads((return_work/'summary.json').read_text())
    completed_receipt(geometry);completed_receipt(source)
    if geometry['status']!='completed-finite-copper-geometry-only-unqualified' or source['status']!='completed-closed-winding-nonlinear-current-response-unqualified' or source['failures']:
        raise ValueError('Need completed saved finite copper and explicit return sources')
    if sha(geometry_work/'copper.brep')!=geometry['brep_sha256']:raise ValueError('Finite copper geometry changed')
    if geometry['translation_m']!=source['translation_m']:raise ValueError('Copper and return coordinate frames differ')
    common=set(geometry['input_hashes'])&set(source['input_hashes'])
    if not common or any(geometry['input_hashes'][p]!=source['input_hashes'][p] for p in common):
        raise ValueError('Finite copper and return do not share the same saved winding inputs')
    import ngsolve as ng
    from netgen.occ import OCCGeometry,Glue
    work.mkdir(parents=True);started=time.monotonic();report={'status':'running','scope':__doc__,'version':ng.__version__,'execution':runtime_metadata(),
        'input_hashes':{str(p):sha(p) for p in [geometry_work/'summary.json',geometry_work/'copper.brep',return_work/'summary.json']},
        'source_snapshots':capture(work,[Path(__file__),Path(__file__).with_name('finite_copper_current.py'),Path(__file__).with_name('finite_copper_geometry.py')]),
        'request':{'mesh_m':args.mesh,'max_dofs':args.max_dofs,'geometry_only':args.geometry_only,'mesh_only':args.mesh_only,'iterative':args.iterative,'port_fraction':args.port_fraction,'geometry_order':args.geometry_order,'pressure_solver':args.pressure_solver}}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        if args.mesh_work:
            mesh_work=args.mesh_work.resolve();prior=json.loads((mesh_work/'summary.json').read_text())
            receipt=json.loads(Path(prior['command_receipt']).read_text())
            if receipt['status'] not in ['completed','failed']:raise ValueError('Reused mesh source has no finished generation receipt')
            if prior['version']!=ng.__version__ or prior['input_hashes']!=report['input_hashes'] or prior['request']['mesh_m']!=args.mesh or prior['request'].get('port_fraction',1.)!=args.port_fraction:
                raise ValueError('Reused finite-copper mesh has different physical inputs or engine')
            if sha(mesh_work/'mesh.vol')!=prior['mesh_sha256'] or sha(mesh_work/'closed-copper.brep')!=prior['brep_sha256']:
                raise ValueError('Reused finite-copper geometry/mesh changed')
            if prior['status']=='running':raise ValueError('Do not import a live mesh trial')
            if (mesh_work/'dc-current-potential.sol').exists():raise ValueError('Mesh-input reuse does not import a prior DC solution')
            for filename in ['mesh.vol','closed-copper.brep']:shutil.copy2(mesh_work/filename,work/filename)
            if sha(work/'mesh.vol')!=prior['mesh_sha256']:raise ValueError('Finite-copper mesh changed while copied')
            report['geometry']=prior['geometry'];report['brep_sha256']=prior['brep_sha256']
            report['mesh_input_reuse']={'work':str(mesh_work),'source_status':prior['status'],'summary_sha256':sha(mesh_work/'summary.json'),
                'scope':'Geometry/mesh inputs only, independently checked hashes/physical inputs. Prior failed solve remains unaccepted; current PDE and all gates rerun.'}
            mesh=ng.Mesh(str(work/'mesh.vol'))
            if prior['request'].get('geometry_order',2)!=args.geometry_order:
                mesh.Curve(args.geometry_order);mesh.ngmesh.Save(str(work/'mesh.vol'))
                report['mesh_input_reuse']['geometry_order_change']=[prior['request'].get('geometry_order',2),args.geometry_order]
        else:
            copper=OCCGeometry(str(geometry_work/'copper.brep')).shape
            points=np.asarray(source['closure']['return_path_m']);layer=geometry['geometry']['layers'][0];width=layer['trace_width_m'];thickness=layer['thickness_m']
            if len(points)!=4:raise ValueError('Current drive-port implementation requires the declared three-segment return')
            segments=[return_prism(a,b,width,thickness) for a,b in zip(points[:-1],points[1:])]
            whole=fuse_all([copper,*segments])
            if len(whole.solids)!=1:raise ValueError('Finite external return does not produce one connected conductor')
            start,end=drive_segment(points,width,args.port_fraction)
            drive=whole*return_prism(start,end,width,thickness);rest=whole-drive;drive.mat('drive');rest.mat('copper')
            report['geometry']={'volume_m3':float(whole.mass),'drive_volume_m3':float(drive.mass),'solid_components':len(whole.solids),
                'return_path_m':points.tolist(),'return_width_m':width,'return_thickness_m':thickness,'drive_path_m':[start.tolist(),end.tolist()],
                'scope':'Finite return scenario, not recovered cable CAD; saved trace width/copper weight used without a fitted radius.'}
            whole.WriteBrep(str(work/'closed-copper.brep'));report['brep_sha256']=sha(work/'closed-copper.brep');save()
        if not args.geometry_only:
            if not args.mesh_work:
                domain=Glue([rest,drive]);domain.maxh=args.mesh
                mesh=ng.Mesh(OCCGeometry(domain).GenerateMesh(maxh=args.mesh));mesh.Curve(args.geometry_order);mesh.ngmesh.Save(str(work/'mesh.vol'))
            report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,materials=list(mesh.GetMaterials()))
            meshed_volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6))
            geometry_error=abs(meshed_volume/report['geometry']['volume_m3']-1)
            report['geometric_volume_check']={'mesh_volume_m3':meshed_volume,'exact_cad_volume_m3':report['geometry']['volume_m3'],'relative_difference':geometry_error,'limit':.02}
            if geometry_error>.02:raise ValueError('Finite copper mesh misses exact-CAD volume gate')
            # RT0 has one flux per face and one scalar per tetrahedron.
            estimate=len(list(mesh.faces))+mesh.ne;report['estimated_dofs']=estimate;save()
            if estimate>args.max_dofs:raise ValueError('Declared finite-copper DC resource cap exceeded before matrix assembly')
            if not args.mesh_only:
                port=np.asarray(report['geometry']['drive_path_m']);vector=port[1]-port[0];length=np.linalg.norm(vector);unit=vector/length
                electric=mesh.MaterialCF({'drive':ng.CoefficientFunction(tuple(unit/length))},default=ng.CoefficientFunction((0.,0.,0.)))
                solution,metadata=solve(ng,mesh,electric,geometry['geometry']['copper_resistivity_ohm_m'],args.iterative,work/'linear-progress.json',args.pressure_solver)
                solution.Save(str(work/'dc-current-potential.sol'));report['solution_sha256']=sha(work/'dc-current-potential.sol')
                report['dc']=dict(metadata,drive_emf_v=1.,effective_loop_current_a=metadata['source_power_w'],
                    effective_loop_resistance_ohm=1/metadata['source_power_w'])
        for p,digest in report['input_hashes'].items():
            if sha(Path(p))!=digest:raise ValueError('Finite circuit input changed')
        for p,entry in report['source_snapshots'].items():
            if sha(Path(p))!=entry['sha256']:raise ValueError('Finite circuit implementation changed')
        status='completed-finite-circuit-geometry-only' if args.geometry_only else ('completed-finite-circuit-mesh-only' if args.mesh_only else 'completed-finite-copper-closed-dc-basis-unqualified')
        report.update(status=status,seconds=time.monotonic()-started);save()
    except BaseException as error:
        if hasattr(error,'details'):report['linear_failure']=error.details
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
