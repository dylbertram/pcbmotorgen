#!/usr/bin/env python3
"""Experimental periodic nonlinear time solve with a finite conducting wall.

Implicit midpoint integrates the full vector magnetic-energy equations, not a
frozen secant permeability. PMs supply DC bias; a sinusoidal coil sheet supplies
the time-dependent perturbation. This tests the small-signal limit and amplitude
envelope of this periodic model only. No moving finite housing, hysteresis, PWM
waveform, imported winding or hardware qualification is implied.
"""
import math

import numpy as np
from scipy.sparse import block_diag, coo_matrix
from scipy.sparse.linalg import spsolve

from spectral_biased_ac import bias_state, complex_response
from spectral_plate import MU0


class Transient:
    def __init__(self,plate,gap=0.0001,wall=0.001,conductivity=25e6,gap_cells=4,wall_cells=32,layer_conductivity=0.):
        if not np.isfinite([gap,wall,conductivity,layer_conductivity]).all() or gap<0 or wall<=0 or min(conductivity,layer_conductivity)<0 or gap_cells<1 or wall_cells<2:
            raise ValueError('Invalid transient tail')
        self.plate=plate;m=plate.modes
        tail=([(gap/gap_cells,0.)]*gap_cells if gap else [])+[(wall/wall_cells,conductivity)]*wall_cells
        self.size=plate.size+len(tail)*m
        rows=[];cols=[];stiffness=[];mass=[]
        def append(r,c,k,v):
            rows.append(r);cols.append(c)
            stiffness.append(np.broadcast_to(k,(m,)));mass.append(np.broadcast_to(v,(m,)))
        bottom=np.arange(plate.size-m,plate.size)
        append(bottom,bottom,-plate.boundary,0.)
        for index,(length,sigma) in enumerate(tail):
            left=bottom+index*m;right=left+m
            diagonal=(1/length+plate.k**2*length/3)/(2*MU0)
            off=(-1/length+plate.k**2*length/6)/(2*MU0)
            append(left,left,diagonal,sigma*length/6)
            append(right,right,diagonal,sigma*length/6)
            append(left,right,off,sigma*length/12)
            append(right,left,off,sigma*length/12)
        last=np.arange(self.size-m,self.size)
        append(last,last,plate.boundary,0.)
        if layer_conductivity:
            for cell in range(plate.cells):
                left=np.arange(cell*m,(cell+1)*m);right=left+m;h=plate.step
                append(left,left,0.,layer_conductivity*h/6)
                append(right,right,0.,layer_conductivity*h/6)
                append(left,right,0.,layer_conductivity*h/12)
                append(right,left,0.,layer_conductivity*h/12)
        coordinates=(np.concatenate(rows),np.concatenate(cols))
        self.stiffness=coo_matrix((np.concatenate(stiffness),coordinates),shape=(self.size,self.size)).tocsr()
        self.mass=coo_matrix((np.concatenate(mass),coordinates),shape=(self.size,self.size)).tocsr()
        self.zero_tail=coo_matrix((self.size-plate.size,self.size-plate.size))
        self.scale=float(np.linalg.norm(plate.incident/MU0))
        if self.scale<=0 or not np.isfinite(self.scale):raise ValueError('Invalid DC source')

    def evaluate(self,vector,hessian=True):
        energy,gradient,matrix=self.plate.evaluate(vector[:self.plate.size],hessian=hessian)
        correction=self.stiffness@vector
        gradient=np.r_[gradient,np.zeros(self.size-self.plate.size)]+correction
        energy+=0.5*float(vector@correction)
        if hessian:matrix=block_diag((matrix,self.zero_tail),format='csr')+self.stiffness
        return energy,gradient,matrix

    def equilibrium(self):
        # Start with the physical DC field; the wall is nonmagnetic. Refine the
        # attached linear tail's FE approximation rather than asserting it is
        # identical to the exact infinite-air map at finite depth resolution.
        p=self.plate
        vector=np.zeros(self.size);vector[:p.size]=p.initial()
        for iteration in range(100):
            energy,gradient,matrix=self.evaluate(vector)
            residual=float(np.linalg.norm(gradient)/self.scale)
            if residual<=1e-9:return vector,{'iterations':iteration+1,'relative_residual':residual}
            direction=spsolve(matrix,-gradient);slope=float(gradient@direction)
            if not np.isfinite(direction).all() or slope>=0:raise ValueError('Invalid nonlinear transient equilibrium direction')
            step=1.
            for _ in range(40):
                candidate=vector+step*direction
                next_energy,next_gradient,_=self.evaluate(candidate,False)
                if next_energy<=energy+1e-4*step*slope or (abs(next_energy-energy)<1e-12*max(1,abs(energy)) and np.linalg.norm(next_gradient)<np.linalg.norm(gradient)):
                    vector=candidate;break
                step*=0.5
            else:raise ValueError('Transient equilibrium line search failed')
        raise ValueError('Transient equilibrium did not converge')

    def step(self,previous,dt,source):
        # Solve for the midpoint itself; A_next=2*A_mid-A_previous. The true
        # Jacobian is H(A_mid)+2*M/dt, including spatial differential coupling.
        midpoint=previous.copy();mass=2*self.mass/dt
        for iteration in range(40):
            _,gradient,matrix=self.evaluate(midpoint)
            residual=gradient+mass@(midpoint-previous)-source
            relative=float(np.linalg.norm(residual)/self.scale)
            if relative<=1e-10:return 2*midpoint-previous,midpoint,relative,iteration+1
            jacobian=matrix+mass;direction=spsolve(jacobian,-residual)
            if not np.isfinite(direction).all():raise ValueError('Nonfinite transient Newton step')
            relaxation=1.
            for _ in range(30):
                candidate=midpoint+relaxation*direction
                next_gradient=self.evaluate(candidate,False)[1]
                next_residual=next_gradient+mass@(candidate-previous)-source
                if np.linalg.norm(next_residual)<np.linalg.norm(residual):midpoint=candidate;break
                relaxation*=0.5
            else:raise ValueError('Transient Newton line search failed')
        raise ValueError('Transient step did not converge')


def run(thickness,mu,bsat,frequency=100e3,fraction=1e-3,phase=0,cells=8,modes=3,samples=128,
        steps_per_period=128,periods=32,wall_cells=32,gap_cells=4):
    if not np.isfinite([frequency,fraction]).all() or min(frequency,fraction)<=0 or phase not in [0,1] or steps_per_period<32 or periods<4:
        raise ValueError('Invalid transient excitation or time resolution')
    plate,hessian,bias_proof=bias_state(thickness,mu,bsat,cells,modes,samples)
    harmonic=complex_response(plate,hessian,frequency,wall_cells=wall_cells,gap_cells=gap_cells)
    transient=Transient(plate,wall_cells=wall_cells,gap_cells=gap_cells)
    vector,equilibrium_proof=transient.equilibrium();equilibrium=vector.copy()
    amplitude=abs(plate.incident[0])*fraction;index=phase*modes
    dt=1/(frequency*steps_per_period);omega=2*math.pi*frequency
    midpoints=[];loss=[];work=[];max_residual=0.;iterations=0
    for step in range(periods*steps_per_period):
        time=(step+0.5)*dt
        source=np.zeros(transient.size);source[index]=amplitude/MU0*math.sin(omega*time)
        next_vector,midpoint,residual,count=transient.step(vector,dt,source)
        derivative=(next_vector-vector)/dt
        if step>=(periods-2)*steps_per_period:
            midpoints.append(midpoint-equilibrium)
            loss.append(float(derivative@(transient.mass@derivative)))
            work.append(float(source@derivative))
        vector=next_vector;max_residual=max(max_residual,residual);iterations+=count
    midpoints=np.asarray(midpoints);last=midpoints[-steps_per_period:];previous=midpoints[:steps_per_period]
    settled=float(np.linalg.norm(last-previous)/max(np.linalg.norm(last),np.finfo(float).tiny))
    if settled>1e-5:raise ValueError(f'Transient has not settled to a periodic state: {settled}')
    time=(np.arange(steps_per_period)+0.5)*dt
    phasor=2*np.mean(last[:,index]*np.exp(-1j*omega*time))
    reflection=plate.k[0]*phasor/(-1j*amplitude)-1
    expected=complex(*harmonic['reflection_per_phase'][phase])
    joule=float(np.mean(loss[-steps_per_period:])/amplitude**2)
    source_work=float(np.mean(work[-steps_per_period:])/amplitude**2)
    balance=abs(source_work/joule-1) if joule>0 else float('inf')
    if not np.isfinite([reflection.real,reflection.imag,joule,balance]).all() or balance>0.02:
        raise ValueError('Nonlinear transient source-work/Joule balance failed')
    # These are sampled diagnostics, not a sharp-edge maximum or a permitted
    # current amplitude. Count actual knee crossings instead of inferring them
    # from the size of the impressed source alone.
    potentials=(last+equilibrium)[:,:plate.size].reshape(steps_per_period,plate.cells+1,plate.modes)
    derivative=np.diff(potentials,axis=1)/plate.step
    knee=bsat*mu/(mu-1);crossing=0.;peak=0.
    for position in [0.5-1/math.sqrt(12),0.5+1/math.sqrt(12)]:
        mid=(1-position)*potentials[:,:-1]+position*potentials[:,1:]
        magnitude=np.hypot(derivative@plate.sine,mid@plate.q)
        crossing+=0.5*float(np.mean((magnitude.min(axis=0)<=knee)&(magnitude.max(axis=0)>knee)))
        peak=max(peak,float(magnitude.max()))
    harmonics=[2*np.mean(last[:,index]*np.exp(-1j*n*omega*time)) for n in range(2,6)]
    distortion=float(np.linalg.norm(harmonics)/abs(phasor))
    return {'scope':__doc__,'frequency_hz':frequency,'fraction_of_pm_fundamental':fraction,'phase':phase,
            'depth_cells':cells,'modes_per_phase':modes,'angular_samples':samples,'wall_cells':wall_cells,'gap_cells':gap_cells,
            'steps_per_period':steps_per_period,'periods':periods,'static_bias_convergence':bias_proof,
            'attached_tail_equilibrium_convergence':equilibrium_proof,'max_step_relative_residual':max_residual,
            'mean_newton_iterations_per_step':iterations/(periods*steps_per_period),'periodic_settlement_relative_change':settled,
            'reflection':[float(reflection.real),float(reflection.imag)],'linearized_reflection':[expected.real,expected.imag],
            'absolute_reflection_difference':abs(reflection-expected),'joule_coefficient_w_m2_t2':joule,
            'linearized_joule_coefficient_w_m2_t2':harmonic['joule_coefficient_w_m2_t2'][phase],
            'source_work_coefficient_w_m2_t2':source_work,'relative_power_balance_error':balance,
            'incident_ripple_peak_b_t':amplitude,'quadrature_sampled_peak_b_t':peak,
            'quadrature_fraction_crossing_knee':crossing,'top_a_harmonics_2_to_5_relative':distortion}
