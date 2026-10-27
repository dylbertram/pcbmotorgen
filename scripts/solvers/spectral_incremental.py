#!/usr/bin/env python3
"""DC differential response around the qualified planar magnet bias.

Add both sine/cosine spatial phases, differentiate the energy equations using
their full differential-reluctivity Hessian, and check with nonlinear finite
differences. This is not a scalar secant mu, a complex AC solve or PWM model.
"""
import math

import numpy as np
from scipy.sparse.linalg import splu, spsolve

from spectral_plate import Plate, MU0


class FullPhasePlate(Plate):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        modes=self.modes;sine=self.sine.copy();cosine=self.cosine.copy();wave=self.k.copy()
        self.harmonics=np.r_[self.harmonics,self.harmonics]
        self.k=np.r_[wave,wave]
        self.sine=np.r_[sine,cosine]
        self.cosine=np.r_[cosine,-sine]
        self.q=np.r_[wave[:,None]*cosine,-wave[:,None]*sine]
        self.incident=np.r_[self.incident,np.zeros(modes)]
        self.ai=self.incident/self.k;self.boundary=self.k/(2*MU0)
        self.modes=2*modes;self.size=(self.cells+1)*self.modes
        self.indices=np.arange(self.size).reshape(self.cells+1,self.modes)
        rows=[];cols=[]
        for i,j in [(0,0),(0,1),(1,0),(1,1)]:
            rows.append(np.broadcast_to(self.indices[i:self.cells+i,:,None],(self.cells,self.modes,self.modes)).ravel())
            cols.append(np.broadcast_to(self.indices[j:self.cells+j,None,:],(self.cells,self.modes,self.modes)).ravel())
        self.rows=np.concatenate(rows);self.cols=np.concatenate(cols)


def newton(plate,initial=None):
    vector=plate.initial() if initial is None else np.asarray(initial).copy()
    scale=float(np.linalg.norm(2*plate.boundary*plate.ai))
    for iteration in range(100):
        energy,gradient,matrix=plate.evaluate(vector)
        residual=float(np.linalg.norm(gradient)/scale)
        if residual<=1e-9:return vector,{'iterations':iteration+1,'relative_gradient_residual':residual}
        direction=spsolve(matrix,-gradient);slope=float(gradient@direction)
        if not np.isfinite(direction).all() or slope>=0:raise ValueError('Invalid differential-bias Newton direction')
        relaxation=1.
        for _ in range(40):
            candidate=vector+relaxation*direction
            next_energy,next_gradient,_=plate.evaluate(candidate,hessian=False)
            if next_energy<=energy+1e-4*relaxation*slope or (abs(next_energy-energy)<1e-12*max(1,abs(energy)) and np.linalg.norm(next_gradient)<np.linalg.norm(gradient)):
                vector=candidate;break
            relaxation*=0.5
        else:raise ValueError('Differential-bias line search failed')
    raise ValueError('Unconverged differential bias')


def response(thickness,mu,bsat,cells=64,modes=17,samples=512,geometry=None,finite_differences=True):
    # Keep the already-qualified static solver/source untouched. The new phase
    # space contains that solution exactly; its extra bias coefficients are zero.
    original=Plate(thickness,mu,bsat,cells,modes,samples,geometry)
    bias,convergence=newton(original)
    full=FullPhasePlate(thickness,mu,bsat,cells,modes,samples,geometry)
    a=np.zeros((cells+1,2*modes));a[:,:modes]=bias.reshape(cells+1,modes)
    vector=a.ravel();_,gradient,hessian=full.evaluate(vector)
    scale=float(np.linalg.norm(2*full.boundary*full.ai))
    if np.linalg.norm(gradient)/scale>1e-9:raise ValueError('Static bias does not solve the extended phase equations')
    rhs=np.zeros((full.size,2));rhs[0,0]=1/MU0;rhs[modes,1]=1/MU0
    differential=splu(hessian.tocsc()).solve(rhs)
    residual=float(np.linalg.norm(hessian@differential-rhs)/np.linalg.norm(rhs))
    if residual>1e-9:raise ValueError('Unconverged incremental tensor solve')
    k=full.k[0]
    reflection=np.array([k*differential[0,0]-1,k*differential[modes,1]-1])
    cross=np.array([k*differential[0,1],k*differential[modes,0]])
    if not np.isfinite(reflection).all() or reflection.min()<-1e-9 or reflection.max()>1+1e-9 or max(abs(cross))>1e-8:
        raise ValueError('Nonpassive or symmetry-breaking incremental response')
    # Match the FEMM benchmark's two isolated finite-thickness current sheets.
    sheet_t=0.00002;ys=np.array([sheet_t/2,full.geometry['pcb']-sheet_t/2])
    if ys[1]<=ys[0]:raise ValueError('PCB cannot contain the two benchmark sheets')
    u=k*sheet_t
    self_weight=2*(u+math.expm1(-u))/(u*u)
    image_weight=(math.sinh(u/2)/(u/2))**2*float(np.mean(np.exp(-2*k*ys)))/self_weight
    factors=1+reflection*image_weight
    sampled_peak=0.;saturated_fraction=0.
    derivative=(a[1:]-a[:-1])/full.step
    for position in [0.5-1/math.sqrt(12),0.5+1/math.sqrt(12)]:
        mid=(1-position)*a[:-1]+position*a[1:]
        magnitude=np.hypot(derivative@full.sine,mid@full.q)
        sampled_peak=max(sampled_peak,float(magnitude.max()))
        saturated_fraction+=0.5*float(np.mean(magnitude>bsat*mu/(mu-1)))
    result={'scope':__doc__,'material':{'thickness_m':thickness,'mu_initial':mu,'saturation_polarization_t':bsat},
            'geometry':full.geometry,'cells':cells,'modes_per_phase':modes,'angle_samples':samples,'bias_convergence':convergence,
            'incremental_linear_residual':residual,'fundamental_reflection_per_phase':reflection.tolist(),
            'cross_phase_reflection':cross.tolist(),'coil_factors_per_phase':factors.tolist(),
            'quadrature_sampled_peak_b_t':sampled_peak,'quadrature_saturated_fraction':saturated_fraction,
            'isolated_sheet_image_weight':image_weight,'finite_differences':[]}
    if finite_differences:
        nominal=full.incident.copy();amplitude=abs(nominal[0])
        for fraction in [1e-4,1e-5]:
            values=[];diagnostics=[]
            for index in [0,modes]:
                potentials=[]
                for sign in [-1,1]:
                    full.incident=nominal.copy();full.incident[index]+=sign*fraction*amplitude
                    full.ai=full.incident/full.k
                    shifted,proof=newton(full,vector)
                    potentials.append(shifted[index]);diagnostics.append(proof)
                derivative=(potentials[1]-potentials[0])/(2*fraction*amplitude)
                values.append(k*derivative-1)
            error=np.abs(np.asarray(values)-reflection)
            if np.any(error>np.maximum(1e-3,0.01*abs(reflection))):
                raise ValueError('Nonlinear finite differences disagree with the tensor response')
            result['finite_differences'].append({'fraction_of_pm_fundamental':fraction,'reflection_per_phase':values,
                                                'absolute_reflection_error':error.tolist(),'nonlinear_convergence':diagnostics})
    return result
