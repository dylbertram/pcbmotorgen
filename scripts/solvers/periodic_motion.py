#!/usr/bin/env python3
"""Nonlinear periodic translating-PM experiment with an infinite-depth wall.

Resolved time-dependent vector saturation and conductor diffusion, with PM
motion impressed through the periodic air-boundary source. Uses BDF2 after one
backward-Euler startup step. This is not finite-array/housing current closure,
imported-winding excitation, hysteresis, demagnetization or hardware validation.
"""
import cmath
import math
import hashlib
from pathlib import Path

import numpy as np
from scipy.sparse.linalg import spsolve

from spectral_transient import Transient
from spectral_biased_ac import bias_state
from spectral_plate import MU0


def moving_source(plate,position):
    """Full incident source and derivative with respect to mechanical X."""
    modes=plate.modes//2;k=plate.k[:modes];incident=plate.incident[:modes]
    theta=k*position
    value=np.r_[incident*np.cos(theta),-incident*np.sin(theta)]/MU0
    derivative=np.r_[-k*incident*np.sin(theta),-k*incident*np.cos(theta)]/MU0
    return value,derivative


def linear_loss(plate,speed,thickness,mu,gap=0.0001,wall=0.001,conductivity=25e6):
    """Independent continuous-depth multilayer limit for all source harmonics."""
    power=0.
    for k,incident in zip(plate.k[:plate.modes//2],plate.incident[:plate.modes//2]):
        omega=k*abs(speed);below=k;g=0j
        for t,mur,sigma in reversed([(thickness,mu,0.),(gap,1.,0.),(wall,1.,conductivity)]):
            gamma=cmath.sqrt(k*k+1j*omega*MU0*mur*sigma);eta=gamma/mur
            rho=(eta-below)/(eta+below)
            g=(rho+g)/(1+rho*g)*cmath.exp(-2*gamma*t);below=eta
        rho=(k-below)/(k+below);reflection=(rho+g)/(1+rho*g)
        power+=-omega*reflection.imag/(MU0*k)*incident**2
    return float(power)


def implicit_step(system,previous,older,dt,source):
    if older is None:
        mass=system.mass/dt;history=previous
    else:
        mass=1.5*system.mass/dt;history=(4*previous-older)/3
    value=previous.copy()
    for iteration in range(40):
        _,gradient,hessian=system.evaluate(value)
        residual=gradient+mass@(value-history)-source
        relative=float(np.linalg.norm(residual)/system.scale)
        if relative<=1e-10:
            derivative=(value-previous)/dt if older is None else (3*value-4*previous+older)/(2*dt)
            return value,derivative,relative,iteration+1
        direction=spsolve(hessian+mass,-residual)
        if not np.isfinite(direction).all():raise ValueError('Nonfinite nonlinear moving step')
        relaxation=1.
        for _ in range(30):
            candidate=value+relaxation*direction
            candidate_residual=system.evaluate(candidate,False)[1]+mass@(candidate-history)-source
            if np.linalg.norm(candidate_residual)<np.linalg.norm(residual):value=candidate;break
            relaxation*=0.5
        else:raise ValueError('Moving nonlinear Newton line search failed')
    raise ValueError('Moving nonlinear time step did not converge')


def sampled_diagnostics(plate,states,mu,bsat):
    states=np.asarray(states)
    potentials=states[:,:plate.size].reshape(len(states),plate.cells+1,plate.modes)
    derivative=np.diff(potentials,axis=1)/plate.step
    knee=bsat*mu/(mu-1);crossing=0.;saturated=0.;peak=0.;minimum=float('inf')
    for position in [0.5-1/math.sqrt(12),0.5+1/math.sqrt(12)]:
        mid=(1-position)*potentials[:,:-1]+position*potentials[:,1:]
        magnitude=np.hypot(derivative@plate.sine,mid@plate.q)
        crossing+=0.5*float(np.mean((magnitude.min(axis=0)<=knee)&(magnitude.max(axis=0)>knee)))
        saturated+=0.5*float(np.mean(magnitude>knee))
        peak=max(peak,float(magnitude.max()));minimum=min(minimum,float(magnitude.min()))
    return {'quadrature_fraction_crossing_knee':crossing,'time_mean_quadrature_saturated_fraction':saturated,
            'quadrature_sampled_peak_b_t':peak,'quadrature_sampled_min_b_t':minimum,
            'scope':'sampled quadrature diagnostics, not a resolved edge maximum or measured material data'}


def save_trace(path,**arrays):
    if path is None:return None
    path=Path(path)
    with path.open('xb') as stream:np.savez_compressed(stream,**arrays)
    return {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def run(speed,thickness=0.0002,mu=130.,bsat=0.25,cells=8,modes=3,samples=128,
        steps_per_period=128,periods=8,wall_cells=16,gap_cells=4,trace_path=None):
    if not np.isfinite(speed) or steps_per_period<32 or periods<4:raise ValueError('Invalid motion/time controls')
    plate,_,bias=bias_state(thickness,mu,bsat,cells,modes,samples)
    system=Transient(plate,wall_cells=wall_cells,gap_cells=gap_cells)
    vector,equilibrium=system.equilibrium()
    base={'scope':__doc__,'speed_m_s':speed,'material':{'thickness_m':thickness,'mu_initial':mu,'saturation_polarization_t':bsat},
          'depth_cells':cells,'modes_per_phase':modes,'angular_samples':samples,'wall_cells':wall_cells,'gap_cells':gap_cells,
          'steps_per_period':steps_per_period,'periods':periods,'bias_convergence':bias,'equilibrium_convergence':equilibrium,
          'geometry':plate.geometry,'wall':{'gap_m':0.0001,'thickness_m':0.001,'conductivity_s_m':25e6}}
    if speed==0:
        return {**base,'joule_w_m2':0.,'source_work_w_m2':0.,'magnet_force_density_n_m2':0.,'mechanical_drag_power_w_m2':0.,
                'relative_drag_joule_error':0.,'relative_source_joule_error':0.,'periodic_settlement_relative_change':0.,
                'max_step_relative_residual':0.,'scope_note':'Static equilibrium; no time integration needed at zero velocity',
                'sampled_material_state':sampled_diagnostics(plate,vector[None,:],mu,bsat),
                'trace':save_trace(trace_path,equilibrium=vector)}
    frequency=abs(speed)*plate.k[0]/(2*math.pi);dt=1/(frequency*steps_per_period)
    states=[];losses=[];forces=[];work=[];older=None;maximum_residual=0.;iterations=0
    for step in range(periods*steps_per_period):
        time=(step+1)*dt;full_source,derivative_x=moving_source(plate,speed*time)
        source=np.zeros(system.size);source[:plate.modes]=full_source-plate.incident/MU0
        next_vector,derivative,residual,count=implicit_step(system,vector,older,dt,source)
        if step>=(periods-2)*steps_per_period:
            states.append(next_vector.copy())
            losses.append(float(derivative@(system.mass@derivative)))
            forces.append(float(derivative_x@next_vector[:plate.modes]))
            work.append(float(full_source@derivative[:plate.modes]))
        older=vector;vector=next_vector;maximum_residual=max(maximum_residual,residual);iterations+=count
    states=np.asarray(states);last=states[-steps_per_period:];before=states[:steps_per_period]
    trace=save_trace(trace_path,states_last_two_periods=states,loss_samples=np.asarray(losses),
                     force_samples=np.asarray(forces),source_work_samples=np.asarray(work),dt_s=np.asarray(dt))
    settled=float(np.linalg.norm(last-before)/max(np.linalg.norm(last),np.finfo(float).tiny))
    if settled>1e-5:raise ValueError(f'Moving solution not periodic: {settled}')
    loss=float(np.mean(losses[-steps_per_period:]));force=float(np.mean(forces[-steps_per_period:]));power=-force*speed
    source_work=float(np.mean(work[-steps_per_period:]))
    drag_error=abs(power/loss-1);source_error=abs(source_work/loss-1)
    if not np.isfinite([loss,force,power,source_work,drag_error,source_error]).all() or loss<=0 or power<=0:
        raise ValueError('Nonpassive or invalid moving response')
    # Numerical time integration must not masquerade as drag. Both independently
    # extracted mechanical work and field-source work must balance Joule heat.
    if max(drag_error,source_error)>0.02:raise ValueError(f'Moving power balance exceeds 2%: drag {drag_error}, source {source_error}')
    return {**base,'frequency_hz':frequency,'joule_w_m2':loss,'source_work_w_m2':source_work,
            'magnet_force_density_n_m2':force,'mechanical_drag_power_w_m2':power,
            'relative_drag_joule_error':drag_error,'relative_source_joule_error':source_error,
            'periodic_settlement_relative_change':settled,'max_step_relative_residual':maximum_residual,
            'mean_newton_iterations_per_step':iterations/(periods*steps_per_period),
            'linear_continuous_depth_loss_w_m2':linear_loss(plate,speed,thickness,mu),
            'sampled_material_state':sampled_diagnostics(plate,last,mu,bsat),'trace':trace}
