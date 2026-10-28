#!/usr/bin/env python3
"""Static full-vector ferrite equilibrium with explicitly resolved nearby air.

The inner air box is a mesh partition only, not an added material or physical
boundary condition. It covers PMs and material bodies, with a declared margin.
This isolates response-field interpolation error from remote-domain truncation.
No winding excitation, induced current or moving-source qualification follows.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from ngsolve_material_motion import magnetic_form
from ngsolve_reduced import source_coefficient
from post_project_force import sha
from post_reduced_force import case_field
from reduced_inputs import validate_reduced_inputs
from solver_threads import add_thread_option,runtime_metadata,threaded_main
from source_snapshot import capture
from tree_gauge import free_dofs


def air_bounds(model,margin,far):
    if not np.isfinite([margin,far]).all() or margin<=0 or far<=0:raise ValueError('Positive finite air controls required')
    objects=model['magnets']+[m for m in model['stack'] if m['name']=='housing' or m['mu_r']>1]
    low=np.min([m['origin_m'] for m in objects],axis=0)-margin
    high=np.max([np.array(m['origin_m'])+m['size_m'] for m in objects],axis=0)+margin
    corners=np.array([[x,y,z] for x in [low[0],high[0]] for y in [low[1],high[1]] for z in [low[2],high[2]]])
    if np.max(np.linalg.norm(corners,axis=1))>=.95*far:raise ValueError('Local air box must fit strictly inside the exterior domain')
    return low,high


def mesh_with_local_air(ng,model,near,fer_near,far,air_mesh,local_mesh,margin):
    from netgen.occ import Box,Sphere,Pnt,OCCGeometry,Glue
    low,high=air_bounds(model,margin,far);bodies=[]
    inner=Box(Pnt(*low),Pnt(*high));inner.faces.name='near_air_interface'
    outer=Sphere(Pnt(0,0,0),far);outer.faces.name='outer'
    exterior=outer-inner;exterior.mat('air');exterior.maxh=air_mesh
    interior=inner
    for layer in model['stack']:
        if layer['name']!='housing' and layer['mu_r']==1:continue
        lo=np.array(layer['origin_m']);hi=lo+layer['size_m'];body=Box(Pnt(*lo),Pnt(*hi))
        body.mat('conductor' if layer['name']=='housing' else layer['name']);body.faces.name='interface'
        size=near if layer['name']=='housing' else fer_near;body.maxh=size;body.faces.maxh=size
        bodies.append(body);interior=interior-body
    interior.mat('air');interior.maxh=local_mesh
    # Apply the local air bound to the mesh-partition faces, while retaining
    # independently specified material-face bounds on the physical bodies.
    for face in interior.faces:
        if face.name=='near_air_interface':face.maxh=local_mesh
    mesh=ng.Mesh(OCCGeometry(Glue([exterior,interior,*bodies])).GenerateMesh(maxh=air_mesh));mesh.Curve(2)
    return mesh,{'minimum_m':low.tolist(),'maximum_m':high.tolist(),'local_air_mesh_m':local_mesh,
        'physical_effect':'none; internal vacuum mesh partition, no Dirichlet condition'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--mesh',type=float,default=.002);parser.add_argument('--fer-mesh',type=float,default=.002)
    parser.add_argument('--far',type=float,default=.04);parser.add_argument('--air-mesh',type=float,default=.01)
    parser.add_argument('--near-air-mesh',type=float,default=.0012);parser.add_argument('--near-air-margin',type=float,default=.002)
    parser.add_argument('--bonus-order',type=int,default=4);parser.add_argument('--max-dofs',type=int,default=700000)
    parser.add_argument('--mesh-only',action='store_true');add_thread_option(parser);args=parser.parse_args()
    work=args.work.resolve();origin=args.source_work.resolve()
    if work.exists():parser.error('Preserve previous refined-air trials')
    controls=[args.mesh,args.fer_mesh,args.far,args.air_mesh,args.near_air_mesh,args.near_air_margin]
    if not np.isfinite(controls).all() or min(controls)<=0 or args.bonus_order<0 or args.max_dofs<1:parser.error('Invalid mesh/resource controls')
    source=json.loads((origin/'summary.json').read_text());case_field(origin,source,'bare');validate_reduced_inputs(origin,source)
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    work.mkdir(parents=True);started=time.monotonic();model=source['model']
    snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
        ['ngsolve_material_motion.py','vector_material.py','ngsolve_reduced.py','tree_gauge.py','solver_threads.py']]])
    report={'status':'running','scope':__doc__,'version':ng.__version__,'model':model,'execution':runtime_metadata(),
        'source_summary_sha256':sha(origin/'summary.json'),'source_snapshots':snapshots,'failures':[],
        'profile':{'start_offset_m':0.,'end_offset_m':0.,'dt_s':.00025,'duration_s':.001},
        'request':dict(mesh=args.mesh,fer_mesh=args.fer_mesh,far=args.far,air_mesh=args.air_mesh,near_air_mesh=args.near_air_mesh,
            near_air_margin=args.near_air_margin,bonus_order=args.bonus_order,order=2,speed=0.,sigma=25e6,steps=4,span=.024,
            start_x=None,save_every=1,static_only=True,mesh_only=args.mesh_only,max_dofs=args.max_dofs)}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        mesh,partition=mesh_with_local_air(ng,model,args.mesh,args.fer_mesh,args.far,args.air_mesh,args.near_air_mesh,args.near_air_margin)
        mesh.ngmesh.Save(str(work/'mesh.vol'));report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,
            mesh_materials=list(mesh.GetMaterials()),local_air_partition=partition)
        if not args.mesh_only:
            space=ng.HCurl(mesh,order=2,nograds=True,dirichlet='outer');report['a_dofs']=space.ndof;report['dofs']=space.ndof;save()
            if space.ndof>args.max_dofs:raise ValueError('Declared refined-air dof/resource cap exceeded')
            selected,_=free_dofs(ng,mesh,space,space);free=np.array(selected,dtype=bool);state=ng.GridFunction(space)
            rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,6+args.bonus_order)}
            source_cf=ng.CacheCF(source_coefficient(ng,model).Compile());form=magnetic_form(ng,space,mesh,model,source_cf,rules)
            residual=state.vec.CreateVector();form.Apply(state.vec,residual);scale=float(np.linalg.norm(residual.FV().NumPy()[free]))
            result=NewtonMinimization(form,state,freedofs=selected,maxit=80,maxerr=1e-12,inverse='sparsecholesky',linesearch=True,printing=True)
            form.Apply(state.vec,residual);relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/max(scale,1e-30)
            report['initial_equilibrium']={'newton_result':list(result),'relative_residual':relative}
            if result[0]!=0 or relative>1e-9:raise ValueError('Refined-air nonlinear equilibrium did not converge')
            state.Save(str(work/'initial-reaction.sol'));report['initial_solution_sha256']=sha(work/'initial-reaction.sol')
        for p,entry in snapshots.items():
            if sha(Path(p))!=entry['sha256']:raise ValueError('Refined-air static implementation changed')
        if sha(origin/'summary.json')!=report['source_summary_sha256']:raise ValueError('Original source/material changed')
        report.update(status='completed-coupled-material-mesh-only' if args.mesh_only else 'completed-coupled-material-static-only',seconds=time.monotonic()-started);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
