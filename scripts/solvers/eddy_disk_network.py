#!/usr/bin/env python3
"""Independent weak-induction current-closure oracle for plain/slotted disks.

Solve -laplacian(u)=1 with u=0 on every boundary of the simply connected
conducting cross-section. The current stream function is -i*sigma*omega*B*u,
so J is divergence free and has no boundary-normal current. Mean loss is
sigma*omega^2*Bpk^2*t*integral(u)/2. This is a prescribed uniform-field,
low-frequency limit, not a full magnetic/diffusion or nonlinear solver.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def shape_integral(n, radius, slot=0):
    if n<16 or radius<=0 or not 0<=slot<radius:
        raise ValueError('Invalid grid or cross-section')
    h=2*radius/n
    if slot and slot<2*h:
        raise ValueError('Resolve the radial slot with at least two grid spacings')
    axis=-radius+(np.arange(n)+0.5)*h
    x,y=np.meshgrid(axis,axis,indexing='ij')
    mask=(x*x+y*y<radius*radius)&~((x>=0)&(abs(y)<slot/2)&(slot>0))
    index=np.full((n,n),-1,dtype=int)
    index[mask]=np.arange(mask.sum())
    rows=[];cols=[];data=[]

    def distance(px,py,coordinate,sign):
        # Exact intersection of the coordinate ray with the circular boundary.
        p,other=(px,py) if coordinate==0 else (py,px)
        boundary=math.sqrt(max(0,radius*radius-other*other))
        d=boundary-sign*p
        if slot:
            if coordinate==0 and abs(py)<slot/2 and px<0 and sign==1:
                d=min(d,-px)
            elif coordinate==1 and px>=0:
                if py>slot/2 and sign==-1:d=min(d,py-slot/2)
                if py<-slot/2 and sign==1:d=min(d,-slot/2-py)
        return d

    for i,j in zip(*np.nonzero(mask)):
        row=index[i,j];diagonal=0.0
        for coordinate in [0,1]:
            neighbours=[];distances=[]
            for sign in [-1,1]:
                ii=i+sign if coordinate==0 else i
                jj=j+sign if coordinate==1 else j
                neighbour=index[ii,jj] if 0<=ii<n and 0<=jj<n else -1
                d=h if neighbour>=0 else distance(x[i,j],y[i,j],coordinate,sign)
                if d<=0:raise ValueError('Invalid boundary intersection')
                neighbours.append(neighbour);distances.append(d)
            dm,dp=distances
            diagonal+=2/(dm*dp)
            for neighbour,d in zip(neighbours,distances):
                if neighbour>=0:
                    rows.append(row);cols.append(neighbour);data.append(-2/(d*(dm+dp)))
        rows.append(row);cols.append(row);data.append(diagonal)
    matrix=coo_matrix((data,(rows,cols)),shape=(mask.sum(),mask.sum())).tocsr()
    u=spsolve(matrix,np.ones(mask.sum()))
    residual=float(np.max(abs(matrix@u-1)))
    if not np.isfinite(u).all() or u.min()<-1e-12*radius*radius or residual>1e-8:
        raise ValueError('Unconverged or nonphysical current stream solution')
    result={'n':n,'spacing_m':h,'unknowns':int(mask.sum()),'integral_u_m4':float(u.sum()*h*h),
            'maximum_residual':residual}
    if not slot:
        exact=(radius*radius-x[mask]**2-y[mask]**2)/4
        result['max_point_error_normalized']=float(np.max(abs(u-exact))/radius**2)
        result['integral_relative_error']=result['integral_u_m4']/(math.pi*radius**4/8)-1
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--n',type=int,nargs='+',default=[96,192,384])
    parser.add_argument('--radius',type=float,default=0.006)
    parser.add_argument('--slot',type=float,nargs='+',default=[0,0.0005])
    parser.add_argument('--frequency',type=float,default=1)
    parser.add_argument('--peak-b',type=float,default=0.01)
    parser.add_argument('--conductivity',type=float,default=25e6)
    parser.add_argument('--thickness',type=float,default=0.001)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if len(args.n)<2 or any(b<=a for a,b in zip(args.n,args.n[1:])):
        parser.error('at least two strictly increasing grids are required')
    if min(args.frequency,args.peak_b,args.conductivity,args.thickness)<=0:
        parser.error('frequency, peak field, conductivity and thickness must be positive')
    request={k:v for k,v in vars(args).items() if not isinstance(v,Path)}
    report={'scope':__doc__,'status':'running','request':request,'cases':{},'failures':[]}
    for slot in args.slot:
        runs=[]
        for n in args.n:
            result=shape_integral(n,args.radius,slot)
            result['mean_power_w']=args.conductivity*(2*math.pi*args.frequency)**2*args.peak_b**2*args.thickness*result['integral_u_m4']/2
            runs.append(result)
        for a,b in zip(runs,runs[1:]):
            if abs(a['mean_power_w']/b['mean_power_w']-1)>0.02:
                report['failures'].append(f'slot {slot:g}: refinement {a["n"]}->{b["n"]} exceeds 2%')
        report['cases'][str(slot)]=runs
        print('slot',slot,'runs',json.dumps(runs),flush=True)
    report['status']='failed' if report['failures'] else 'passed-weak-limit'
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
