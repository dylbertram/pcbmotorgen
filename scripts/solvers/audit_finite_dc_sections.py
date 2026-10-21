#!/usr/bin/env python3
"""Integrate linear-tetrahedron DC currents on explicit planar cross-sections.

Sections are clipped geometrically, not sampled with a smeared volume delta.
Return checks alone do not qualify all winding branches or magnetic sources.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_finite_dc_controls import MIXED,load
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def clip_polygon(points,axis,bound,sign):
    output=[]
    for a,b in zip(points,np.roll(points,-1,axis=0)):
        da=bound-sign*a[axis];db=bound-sign*b[axis]
        if da>=0:output.append(a)
        if (da<0)!=(db<0):output.append(a+(b-a)*da/(da-db))
    return np.asarray(output)


def section(mesh,current,tetrahedra,centre,normal,radius):
    centre=np.asarray(centre,dtype=float);normal=np.asarray(normal,dtype=float)
    if centre.shape!=(3,) or normal.shape!=(3,) or not np.isfinite([centre,normal]).all() or np.linalg.norm(normal)==0 or not np.isfinite(radius) or radius<=0:
        raise ValueError('Invalid DC section')
    normal=normal/np.linalg.norm(normal);seed=np.eye(3)[np.argmin(abs(normal))]
    u=np.cross(normal,seed);u/=np.linalg.norm(u);v=np.cross(normal,u)
    distances=(tetrahedra-centre)@normal
    extent=np.sqrt(2)*radius
    # Half-open ownership counts an internal face exactly once when the plane
    # is coplanar with it. Strict crossing alone would omit both neighbours.
    candidates=(distances.min(axis=1)<0)&(distances.max(axis=1)>=0)
    candidates&=np.all(tetrahedra.min(axis=1)<=centre+extent,axis=1)&np.all(tetrahedra.max(axis=1)>=centre-extent,axis=1)
    flux=0.;area=0.;triangles=0
    for tet,d in zip(tetrahedra[candidates],distances[candidates]):
        points=[]
        for i in range(4):
            if d[i]==0:points.append(tet[i])
            for j in range(i+1,4):
                if d[i]*d[j]<0:points.append(tet[i]+(tet[j]-tet[i])*d[i]/(d[i]-d[j]))
        if len(points)<3:continue
        points=np.unique(np.asarray(points),axis=0)-centre
        p=np.column_stack([points@u,points@v]);mid=p.mean(axis=0)
        p=p[np.argsort(np.arctan2(p[:,1]-mid[1],p[:,0]-mid[0]))]
        for axis in [0,1]:
            for sign in [-1,1]:
                p=clip_polygon(p,axis,radius,sign)
                if len(p)<3:break
            if len(p)<3:break
        if len(p)<3:continue
        for i in range(1,len(p)-1):
            a,b,c=p[0],p[i],p[i+1];ab=b-a;ac=c-a
            weight=abs(ab[0]*ac[1]-ab[1]*ac[0])/2
            if weight<=1e-30:continue
            mid=(a+b+c)/3;point=centre+mid[0]*u+mid[1]*v
            value=np.asarray(current(mesh(*point)),dtype=float)
            flux+=weight*float(value@normal);area+=weight;triangles+=1
    if not triangles or not np.isfinite([area,flux]).all():raise ValueError('Empty/nonfinite DC section')
    return {'current_a':float(flux),'area_m2':float(area),'triangles':triangles,'centre_m':centre.tolist(),
        'normal':normal.tolist(),'window_half_width_m':radius}


def tetrahedra(mesh):
    vertices=np.array([tuple(v.point) for v in mesh.vertices]);indices=np.array([[v.nr for v in e.vertices] for e in mesh.Elements()])
    if indices.ndim!=2 or indices.shape[1]!=4:raise ValueError('DC sections require tetrahedra')
    return vertices[indices]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);add_thread_option(parser);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier section audits')
    work=args.work.resolve();source=load(work,MIXED)
    if source['request']['geometry_order']!=1:raise ValueError('Curved section maps are unsupported')
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('DC section engine version differs')
    mesh=ng.Mesh(str(work/'mesh.vol'));space=ng.HDiv(mesh,order=0)*ng.L2(mesh,order=0)
    solution=ng.GridFunction(space);solution.Load(str(work/'dc-current-potential.sol'));tets=tetrahedra(mesh)
    path=np.asarray(source['geometry']['return_path_m']);delta=path[2]-path[1]
    # The straight middle branch is clear of the end bends at these positions.
    records=[];failures=[];expected=source['dc']['effective_loop_current_a']
    for fraction in [.3,.45,.55,.7]:
        centre=path[1]+fraction*delta
        record=section(mesh,solution.components[0],tets,centre,delta,source['geometry']['return_width_m'])
        record['relative_current_error']=abs(record['current_a']/expected-1)
        record['relative_area_error']=abs(record['area_m2']/(source['geometry']['return_width_m']*source['geometry']['return_thickness_m'])-1)
        record['passed']=record['relative_current_error']<=1e-8 and record['relative_area_error']<=1e-8
        records.append(record)
        if not record['passed']:failures.append(f'return section {fraction}')
    report={'status':('failed' if failures else 'passed')+'-finite-dc-return-sections-only','scope':__doc__,
        'source_summary_sha256':sha(work/'summary.json'),'source_solution_sha256':source['solution_sha256'],
        'source_work':str(work),'execution':runtime_metadata(),'expected_loop_current_a':expected,
        'sections':records,'failures':failures,'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if failures:raise ValueError('Finite DC return cross-section control failed')


if __name__=='__main__':threaded_main(main)
