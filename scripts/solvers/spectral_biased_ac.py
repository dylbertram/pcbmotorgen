"""Experimental complex small-signal A solve around a static spectral bias.

The frozen coefficient is the full differential-reluctivity Hessian, not secant
mu and not an oscillating PM. A finite Al wall and air gap form a linear tail.
This is periodic/infinite-depth 2D A_z physics; no finite current return paths,
hysteresis or nonlinear time-domain/PWM qualification follows from it.
"""
import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu

from spectral_plate import Plate, MU0
from spectral_incremental import FullPhasePlate, newton


def bias_state(thickness,mu,bsat,cells,modes,samples,geometry=None):
    base=Plate(thickness,mu,bsat,cells,modes,samples,geometry)
    bias,proof=newton(base)
    full=FullPhasePlate(thickness,mu,bsat,cells,modes,samples,geometry)
    vector=np.zeros((cells+1,2*modes));vector[:,:modes]=bias.reshape(cells+1,modes)
    _,gradient,matrix=full.evaluate(vector.ravel())
    if np.linalg.norm(gradient)/np.linalg.norm(2*full.boundary*full.ai)>1e-9:
        raise ValueError('Extended static bias is unconverged')
    return full,matrix,proof


def complex_response(full,hessian,frequency,gap=0.0001,wall=0.001,conductivity=25e6,
                     gap_cells=4,wall_cells=32,layer_conductivity=0):
    if not (np.isfinite([frequency,gap,wall,conductivity,layer_conductivity]).all() and frequency>=0 and gap>=0 and wall>0 and
            conductivity>=0 and layer_conductivity>=0 and gap_cells>=1 and wall_cells>=2):
        raise ValueError('Invalid linear tail or excitation')
    omega=2*math.pi*frequency;m=full.modes
    tail=[(gap/gap_cells,0.)]*gap_cells if gap else []
    tail += [(wall/wall_cells,conductivity)]*wall_cells
    total=full.size+len(tail)*m
    original=hessian.tocoo()
    rows=[original.row];cols=[original.col];data=[original.data.astype(complex)]
    # Remove the old exact bottom-air map, attach the gap/wall and put the map
    # at its new bottom. Linear tail modes are uncoupled; the biased layer is not.
    old_bottom=np.arange(full.size-m,full.size)
    rows.append(old_bottom);cols.append(old_bottom);data.append(-full.boundary.astype(complex))
    elements=[]

    def add_segment(left,length,sigma,mu=1):
        right=left+m
        diagonal=(1/length+full.k**2*length/3)/(2*MU0*mu)
        off=(-1/length+full.k**2*length/6)/(2*MU0*mu)
        mass_diagonal=1j*omega*sigma*length/6
        mass_off=1j*omega*sigma*length/12
        for r,c,v in [(left,left,diagonal+mass_diagonal),(right,right,diagonal+mass_diagonal),
                      (left,right,off+mass_off),(right,left,off+mass_off)]:
            rows.append(r);cols.append(c);data.append(np.broadcast_to(v,(m,)).astype(complex))
        elements.append((left,right,length,sigma))

    if layer_conductivity:
        # The magnetic stiffness is already in the nonlinear-bias Hessian.
        for cell in range(full.cells):
            left=np.arange(cell*m,(cell+1)*m);right=left+m;length=full.step
            for r,c,v in [(left,left,1j*omega*layer_conductivity*length/6),
                          (right,right,1j*omega*layer_conductivity*length/6),
                          (left,right,1j*omega*layer_conductivity*length/12),
                          (right,left,1j*omega*layer_conductivity*length/12)]:
                rows.append(r);cols.append(c);data.append(np.full(m,v,dtype=complex))
            elements.append((left,right,length,layer_conductivity))
    for cell,(length,sigma) in enumerate(tail):
        add_segment(old_bottom+cell*m,length,sigma)
    bottom=np.arange(total-m,total)
    rows.append(bottom);cols.append(bottom);data.append(full.boundary.astype(complex))
    matrix=coo_matrix((np.concatenate(data),(np.concatenate(rows),np.concatenate(cols))),shape=(total,total)).tocsc()
    rhs=np.zeros((total,2),dtype=complex);fundamental_modes=m//2
    rhs[0,0]=1/MU0;rhs[fundamental_modes,1]=1/MU0
    solution=splu(matrix).solve(rhs)
    residual=float(np.linalg.norm(matrix@solution-rhs)/np.linalg.norm(rhs))
    if residual>1e-9:raise ValueError('Unconverged complex tensor solve')
    k=full.k[0]
    reflection=np.array([k*solution[0,0]-1,k*solution[fundamental_modes,1]-1])
    cross=np.array([k*solution[0,1],k*solution[fundamental_modes,0]])
    if not np.isfinite(reflection).all() or np.any(abs(reflection)>1+1e-7) or np.any(reflection.imag>1e-8):
        raise ValueError('Nonpassive complex reflection')
    if np.max(abs(cross))>1e-8:raise ValueError('Unexpected cross-phase response for the symmetric bias')
    # Unit incident B is a normalized Green response, not a physical 1 T ripple.
    # Temporal and spatial averages each supply 1/2 in Joule heating.
    joule=np.zeros(2)
    for left,right,length,sigma in elements:
        a,b=solution[left],solution[right]
        integral=length/3*np.sum(abs(a)**2+abs(b)**2+np.real(a*np.conjugate(b)),axis=0)
        joule+=sigma*omega**2/4*integral
    source_work=-omega*reflection.imag/(2*MU0*k)
    if omega>0 and (conductivity>0 or layer_conductivity>0) and np.any(abs(joule-source_work)>1e-8*np.maximum(abs(joule),1e-20)):
        raise ValueError('Normalized source-work/Joule power balance failed')
    sheet_t=0.00002;ys=np.array([sheet_t/2,full.geometry['pcb']-sheet_t/2]);u=k*sheet_t
    self_weight=2*(u+math.expm1(-u))/(u*u)
    weight=(math.sinh(u/2)/(u/2))**2*float(np.mean(np.exp(-2*k*ys)))/self_weight
    factors=1+weight*reflection
    return {'frequency_hz':frequency,'wall_cells':wall_cells,'gap_cells':gap_cells,'linear_residual':residual,
            'tail':{'gap_m':gap,'wall_thickness_m':wall,'wall_conductivity_s_m':conductivity,'layer_conductivity_s_m':layer_conductivity},
            'reflection_per_phase':[[float(v.real),float(v.imag)] for v in reflection],
            'cross_phase_reflection':[[float(v.real),float(v.imag)] for v in cross],
            'coil_factors_per_phase':[[float(v.real),float(v.imag)] for v in factors],
            'joule_coefficient_w_m2_t2':joule.tolist(),'source_work_coefficient_w_m2_t2':source_work.tolist(),
            'unit_source_scope':'normalized linear response per squared incident T, not a 1 T nonlinear ripple claim'}
