#!/usr/bin/env python3
"""Independent finite 3D motional-current oracle in the weak-induction limit.

Magpylib supplies the prescribed PM field. SciPy solves charge continuity on
a closed finite-volume resistor grid with J=sigma*(-grad(phi)+v_cross_B).
There are no exterior current edges. This is an induced-current solve, not
uncompensated sigma*v_cross_B, but it omits magnetic reaction and memory.
It cannot qualify operating-speed housing drag when magnetic Reynolds number
is not small. Velocity is that of the conductor in the stationary-PM frame.
"""
import argparse
import json
import math
from pathlib import Path

import magpylib as magpy
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve

MU0=4e-7*math.pi


def solve(shape, dimensions, velocity, conductivity, field, slot=0):
    shape=np.asarray(shape,dtype=int);dimensions=np.asarray(dimensions,dtype=float)
    velocity=np.asarray(velocity,dtype=float)
    if shape.shape!=(3,) or np.any(shape<2) or dimensions.shape!=(3,) or not np.isfinite(dimensions).all() or np.any(dimensions<=0) or not np.isfinite(conductivity) or conductivity<=0:
        raise ValueError('Invalid finite conductor grid')
    if velocity.shape!=(3,) or not np.isfinite(velocity).all() or not 0<=slot<dimensions[1]:
        raise ValueError('Invalid velocity or slot')
    requested_shape=shape.copy()
    edges=[np.linspace(-dimensions[i]/2,dimensions[i]/2,shape[i]+1) for i in range(3)]
    if slot:
        # Insert physical slot faces, avoiding a mesh-dependent removed volume.
        for axis,faces in [(0,[0]),(1,[-slot/2,0,slot/2])]:
            for face in faces:
                if np.min(abs(edges[axis]-face))>1e-12*dimensions[axis]:
                    edges[axis]=np.sort(np.r_[edges[axis],face])
    edges[2]-=dimensions[2]/2  # plate top at z=0
    widths=[np.diff(a) for a in edges]
    axes=[(a[1:]+a[:-1])/2 for a in edges]
    shape=np.array([len(a) for a in axes])
    points=np.stack(np.meshgrid(*axes,indexing='ij'),axis=-1)
    volumes=np.einsum('i,j,k->ijk',*widths)
    mask=np.ones(tuple(shape),dtype=bool)
    if slot:mask&=~((points[...,0]>=0)&(abs(points[...,1])<slot/2))
    index=np.full(tuple(shape),-1,dtype=int);index[mask]=np.arange(mask.sum())
    starts=[];ends=[];directions=[];conductances=[];lengths=[];locations=[]
    for axis in range(3):
        a=[slice(None)]*3;b=[slice(None)]*3
        a[axis]=slice(None,-1);b[axis]=slice(1,None)
        a,b=tuple(a),tuple(b)
        live=mask[a]&mask[b]
        count=int(live.sum())
        view=[1,1,1];view[axis]=shape[axis]
        width=np.broadcast_to(widths[axis].reshape(view),tuple(shape))
        distance=(width[a][live]+width[b][live])/2
        area=volumes[a][live]/width[a][live]
        starts.append(index[a][live]);ends.append(index[b][live])
        directions.append(np.full(count,axis,dtype=int))
        lengths.append(distance)
        conductances.append(conductivity*area/distance)
        locations.append((points[a][live]+points[b][live])/2)
    start,end=np.concatenate(starts),np.concatenate(ends)
    direction=np.concatenate(directions);length=np.concatenate(lengths);g=np.concatenate(conductances)
    locations=np.concatenate(locations)
    b=np.asarray(field(locations))
    if b.shape!=locations.shape or not np.isfinite(b).all():raise ValueError('Invalid prescribed field')
    basis=np.eye(3)[direction]
    emf=(np.cross(velocity,b)*basis).sum(axis=1)*length
    rows=np.r_[start,end,start,end];cols=np.r_[start,end,end,start]
    matrix=coo_matrix((np.r_[g,g,-g,-g],(rows,cols)),shape=(mask.sum(),mask.sum())).tocsr()
    rhs=-np.bincount(start,weights=g*emf,minlength=mask.sum())+np.bincount(end,weights=g*emf,minlength=mask.sum())
    count,labels=connected_components(matrix,directed=False)
    # Each isolated conductor needs its own potential reference, not a fake bus.
    references=np.array([np.flatnonzero(labels==i)[0] for i in range(count)])
    free=np.ones(mask.sum(),dtype=bool);free[references]=False
    potential=np.zeros(mask.sum())
    potential[free]=spsolve(matrix[free][:,free],rhs[free])
    current=g*(potential[start]-potential[end]+emf)
    kcl=np.bincount(start,weights=current,minlength=mask.sum())-np.bincount(end,weights=current,minlength=mask.sum())
    power=float(np.sum(current*current/g))
    source=float(current@emf)
    force=np.sum((current*length)[:,None]*np.cross(basis,b),axis=0)
    uninhibited=float(np.sum(g*emf*emf))
    scale=max(uninhibited,power,1e-30)
    balance=abs(source-power)/scale
    if balance>1e-10 or abs(float(force@velocity)+source)>1e-10*scale:
        raise ValueError('Charge or mechanical/electrical power balance failed')
    current_scale=max(float(np.max(abs(g*emf))),1e-30)
    residual=float(np.max(abs(kcl)))/current_scale
    if residual>1e-9:raise ValueError('Unconverged current-continuity solve')
    return {'shape':shape.tolist(),'requested_shape':requested_shape.tolist(),'cells':int(mask.sum()),'edges':len(current),'components':int(count),
            'conductor_volume_m3':float(volumes[mask].sum()),
            'velocity_m_s':velocity.tolist(),'force_on_conductor_n':force.tolist(),'joule_power_w':power,
            'motional_source_power_w':source,'uninhibited_power_w':uninhibited,'normalized_power_balance_error':balance,
            'relative_kcl_residual':residual,'magnetic_reynolds_number':MU0*conductivity*np.linalg.norm(velocity)*max(dimensions)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grids',type=int,nargs='+',default=[24,36,48])
    parser.add_argument('--depth-cells',type=int,nargs='+',default=[4,6,8])
    parser.add_argument('--dimensions',type=float,nargs=3,default=[0.012,0.012,0.001])
    parser.add_argument('--velocity',type=float,nargs=3,default=[0.01,0,0])
    parser.add_argument('--conductivity',type=float,default=25e6)
    parser.add_argument('--slot',type=float,default=0)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if len(args.grids)!=len(args.depth_cells) or len(args.grids)<2:
        parser.error('provide at least two corresponding lateral/depth refinements')
    if any(b<=a for sequence in [args.grids,args.depth_cells] for a,b in zip(sequence,sequence[1:])):
        parser.error('lateral and depth grids must each strictly increase')
    rm=MU0*args.conductivity*np.linalg.norm(args.velocity)*max(args.dimensions)
    if not np.isfinite(rm) or rm>0.01:parser.error('magnetic reaction is omitted; require finite magnetic Reynolds number <=0.01')
    magnet=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028))
    request={k:v for k,v in vars(args).items() if not isinstance(v,Path)}
    report={'scope':__doc__,'status':'running','request':request,'runs':[],'failures':[]}
    for n,nz in zip(args.grids,args.depth_cells):
        result=solve([n,n,nz],args.dimensions,args.velocity,args.conductivity,magnet.getB,args.slot)
        report['runs'].append(result)
        print(json.dumps(result),flush=True)
    for a,b in zip(report['runs'],report['runs'][1:]):
        change=abs(a['joule_power_w']/b['joule_power_w']-1)
        if change>0.02:report['failures'].append(f'{a["shape"]}->{b["shape"]}: loss change {change:.2%} exceeds 2%')
    report['status']='failed' if report['failures'] else 'passed-prescribed-field-limit'
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
