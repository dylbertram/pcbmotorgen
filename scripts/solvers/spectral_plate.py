#!/usr/bin/env python3
"""Experimental planar nonlinear Fourier-Galerkin plate reference.

Retains coupled odd spatial modes of A, rather than fitting one scalar mu.
Minimizes the convex magnetic energy of the exact vector two-slope law.
Air above/below is eliminated analytically by its Dirichlet-to-Neumann map.
Depth uses linear elements with two-point Gauss integration; x is periodic.
This is a reduced planar experiment, not finite housing/current/AC physics and
not a proposed native Rust FEM backend. No constants are fitted to FEMM.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from check_plate2d import reference
from vector_harmonic_screen import source, MU0


def constitutive(x,z,mu,bsat):
    norm=np.hypot(x,z);knee=bsat*mu/(mu-1)
    saturated=norm>knee;delta=np.maximum(norm-knee,0)
    nu=np.full_like(norm,1/(MU0*mu))
    nu[saturated]=(norm[saturated]-bsat)/(MU0*norm[saturated])
    energy=np.where(saturated,knee*knee/(2*MU0*mu)+knee/(MU0*mu)*delta+delta*delta/(2*MU0),norm*norm/(2*MU0*mu))
    extra=np.zeros_like(norm);extra[saturated]=bsat/(MU0*norm[saturated]**3)
    return energy,nu*x,nu*z,nu+extra*x*x,extra*x*z,nu+extra*z*z


class Plate:
    def __init__(self,thickness,mu,bsat,cells,modes,samples=256,geometry=None):
        if not (np.isfinite([thickness,mu,bsat]).all() and thickness>0 and mu>1 and bsat>0 and cells>=2 and modes>=1 and samples>=8*modes):
            raise ValueError('Invalid planar material or spectral resolution')
        self.thickness=thickness;self.mu=mu;self.bsat=bsat;self.cells=cells;self.modes=modes;self.samples=samples
        self.geometry={'pole_pitch':0.006,'pcb':0.0008,'gap':0.0005,'width':0.005,'height':0.003,'br':1.34}
        if geometry:
            if set(geometry)-set(self.geometry):raise ValueError('Unknown periodic geometry fields')
            self.geometry.update(geometry)
        if not all(np.isfinite(v) and v>0 for v in self.geometry.values()) or self.geometry['width']>=self.geometry['pole_pitch']:
            raise ValueError('Invalid periodic source geometry')
        self.step=thickness/cells
        self.harmonics=np.arange(1,2*modes,2)
        self.k=self.harmonics*math.pi/self.geometry['pole_pitch']
        theta=(np.arange(samples)+0.5)*2*math.pi/samples
        self.sine=np.sin(self.harmonics[:,None]*theta);self.cosine=np.cos(self.harmonics[:,None]*theta)
        self.q=self.k[:,None]*self.cosine
        source_args={key:value for key,value in self.geometry.items() if key!='pole_pitch'}
        self.incident=np.array([source(float(k),int(n),**source_args) for k,n in zip(self.k,self.harmonics)])
        self.ai=self.incident/self.k
        self.boundary=self.k/(2*MU0)
        self.size=(cells+1)*modes
        self.indices=np.arange(self.size).reshape(cells+1,modes)
        # Rows/columns for neighbouring depth-node blocks, fixed across Newton.
        rows=[];cols=[]
        for i,j in [(0,0),(0,1),(1,0),(1,1)]:
            rows.append(np.broadcast_to(self.indices[i:cells+i,:,None],(cells,modes,modes)).ravel())
            cols.append(np.broadcast_to(self.indices[j:cells+j,None,:],(cells,modes,modes)).ravel())
        self.rows=np.concatenate(rows);self.cols=np.concatenate(cols)

    def initial(self):
        depth=np.linspace(0,self.thickness,self.cells+1)
        return (self.ai[None,:]*np.exp(-depth[:,None]*self.k)).ravel()

    def evaluate(self,vector,hessian=True):
        a=np.asarray(vector).reshape(self.cells+1,self.modes)
        gradient=np.zeros_like(a);energy=0.
        blocks=[np.zeros((self.cells,self.modes,self.modes)) for _ in range(4)] if hessian else None
        derivative=(a[1:]-a[:-1])/self.step
        for position in [0.5-1/math.sqrt(12),0.5+1/math.sqrt(12)]:
            mid=(1-position)*a[:-1]+position*a[1:]
            x=derivative@self.sine;z=mid@self.q
            w,hx,hz,dxx,dxz,dzz=constitutive(x,z,self.mu,self.bsat)
            energy+=self.step*0.5*float(w.mean(axis=1).sum())
            gx=hx@self.sine.T/self.samples;gz=hz@self.q.T/self.samples
            gradient[:-1]+=0.5*(-gx+self.step*(1-position)*gz)
            gradient[1:]+=0.5*(gx+self.step*position*gz)
            if hessian:
                def correlation(weight,left,right):
                    return np.einsum('cs,is,js->cij',weight,left,right,optimize=True)/self.samples
                xx=correlation(dxx,self.sine,self.sine)
                zz=correlation(dzz,self.q,self.q)
                xz=correlation(dxz,self.sine,self.q);zx=xz.transpose(0,2,1)
                blocks[0]+=0.5*(xx/self.step+self.step*(1-position)**2*zz-(1-position)*(xz+zx))
                blocks[3]+=0.5*(xx/self.step+self.step*position**2*zz+position*(xz+zx))
                cross=0.5*(-xx/self.step+self.step*position*(1-position)*zz-position*xz+(1-position)*zx)
                blocks[1]+=cross;blocks[2]+=cross.transpose(0,2,1)
        top=a[0]-2*self.ai;bottom=a[-1]
        energy+=0.5*float(self.boundary@(top*top+bottom*bottom))
        gradient[0]+=self.boundary*top;gradient[-1]+=self.boundary*bottom
        if not hessian:return energy,gradient.ravel(),None
        matrix=coo_matrix((np.concatenate([b.ravel() for b in blocks]),(self.rows,self.cols)),shape=(self.size,self.size)).tocsr()
        diagonal=np.zeros(self.size);diagonal[:self.modes]=self.boundary;diagonal[-self.modes:]=self.boundary
        matrix.setdiag(matrix.diagonal()+diagonal)
        return energy,gradient.ravel(),matrix


def solve(thickness,mu,bsat,cells,modes,samples=256,geometry=None):
    import time
    started=time.monotonic()
    plate=Plate(thickness,mu,bsat,cells,modes,samples,geometry);vector=plate.initial()
    scale=float(np.linalg.norm(2*plate.boundary*plate.ai))
    for iteration in range(100):
        energy,gradient,matrix=plate.evaluate(vector)
        residual=float(np.linalg.norm(gradient)/scale)
        if residual<=1e-9:break
        direction=spsolve(matrix,-gradient)
        slope=float(gradient@direction)
        if not np.isfinite(direction).all() or slope>=0:raise ValueError('Invalid Newton energy direction')
        relaxation=1.
        for _ in range(40):
            trial=vector+relaxation*direction
            next_energy,next_gradient,_=plate.evaluate(trial,hessian=False)
            # Permit roundoff-size energy changes only if the true residual falls.
            if next_energy<=energy+1e-4*relaxation*slope or (abs(next_energy-energy)<1e-12*max(1,abs(energy)) and np.linalg.norm(next_gradient)<np.linalg.norm(gradient)):
                vector=trial;break
            relaxation*=0.5
        else:raise ValueError('Newton energy line search failed')
    else:raise ValueError('Coupled spectral nonlinearity did not converge')
    a=vector.reshape(cells+1,modes);reflected=plate.k*a[0]-plate.incident
    pcb=plate.geometry['pcb']
    bare=float(np.sum(plate.incident*np.exp(plate.k*pcb)))
    image=float(np.sum(reflected*np.exp(-plate.k*pcb)))
    pressure=float(np.sum(plate.incident*reflected)/MU0*plate.geometry['pole_pitch']/plate.geometry['width'])
    return {'cells':cells,'modes':modes,'angle_samples':samples,'newton_iterations':iteration+1,
            'material':{'thickness_m':thickness,'mu_initial':mu,'saturation_polarization_t':bsat},
            'relative_gradient_residual':residual,'field_ratio':1+image/bare,'pressure_pa':pressure,
            'reflected_normal_modes_t':reflected.tolist(),'geometry':plate.geometry,'seconds':time.monotonic()-started}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--femm-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cells',type=int,nargs='+',default=[32,64])
    parser.add_argument('--modes',type=int,nargs='+',default=[9,17])
    parser.add_argument('--angle-samples',type=int,default=512)
    args=parser.parse_args()
    if len(args.cells)<2 or len(args.modes)<2 or any(b<=a for seq in [args.cells,args.modes] for a,b in zip(seq,seq[1:])):
        parser.error('provide separate increasing depth and harmonic refinements')
    report={'scope':__doc__,'status':'running','cases':{},'failures':[],
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_kernel_sha256':hashlib.sha256((Path(__file__).parent/'vector_harmonic_screen.py').read_bytes()).hexdigest()}
    base=reference(args.femm_work/'v2.none.mag.out')
    for name,t,mu,bsat in [('flex_0.1',0.0001,130,0.25),('flex_0.2',0.0002,130,0.25),
                           ('flex_1',0.001,130,0.25),('flex_5',0.005,130,0.25),('mnzn_2',0.002,2500,0.45)]:
        path=args.femm_work/f'v2.{name}.knee.out';ref=reference(path)
        expected_ratio=ref['mag_centre_pcb_top_By']/base['mag_centre_pcb_top_By'];expected_pressure=ref['Fy_stack']/0.01
        runs={}
        levels=[('base',args.cells[0],args.modes[0]),('depth',args.cells[-1],args.modes[0]),('modes',args.cells[-1],args.modes[-1])]
        for label,cells,modes in levels:
            result=solve(t,mu,bsat,cells,modes,args.angle_samples)
            result.update(field_ratio_error=result['field_ratio']/expected_ratio-1,pressure_error=result['pressure_pa']/expected_pressure-1)
            runs[label]=result;print(name,label,json.dumps(result),flush=True)
        for first,second in [('base','depth'),('depth','modes')]:
            for key in ['field_ratio','pressure_pa']:
                if abs(runs[first][key]/runs[second][key]-1)>0.02:report['failures'].append(f'{name}: {first}->{second} {key} exceeds 2%')
        if abs(runs['modes']['field_ratio_error'])>0.05 or abs(runs['modes']['pressure_error'])>0.05:
            report['failures'].append(f'{name}: FEMM field/force agreement exceeds 5%')
        report['cases'][name]={'runs':runs,'reference_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    report['status']='rejected-experiment' if report['failures'] else 'comparison-only'
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
