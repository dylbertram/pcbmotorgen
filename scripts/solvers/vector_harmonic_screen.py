#!/usr/bin/env python3
"""Experimental biaxial harmonic saturation closure, not a production model.

Project the isotropic vector B(H) law onto Hx*sin(kx), Hz*cos(kx) separately.
This gives two fundamental permeabilities and a linear anisotropic layer solve.
Depth cells are refined independently. Higher source harmonics see the frozen
fundamental-bias closure, so harmonic mixing is omitted. No FEMM constant fit.
This experiment must be rejected if independent reference gates do not pass.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from check_plate2d import reference

MU0=4e-7*math.pi


def projection(mu_initial, bsat, hx, hz, samples=512):
    """Fourier projection of B=mu0*H+min(mu0*(mui-1)*|H|,Bsat)*H/|H|."""
    hx,hz=np.broadcast_arrays(np.asarray(hx,dtype=float),np.asarray(hz,dtype=float))
    theta=(np.arange(samples)+0.5)*math.pi/(2*samples)
    sine,cosine=np.sin(theta),np.cos(theta)
    norm=np.hypot(hx[...,None]*sine,hz[...,None]*cosine)
    secant=1+np.minimum(mu_initial-1,bsat/np.maximum(MU0*norm,np.finfo(float).tiny))
    return (2*np.mean(secant*sine*sine,axis=-1),2*np.mean(secant*cosine*cosine,axis=-1))


def fields(k, thicknesses, mux, muz, incident=1):
    """Exact anisotropic linear-layer solution for each cell's midplane H."""
    t=np.asarray(thicknesses);mux=np.asarray(mux);muz=np.asarray(muz)
    gamma=k*np.sqrt(mux/muz);eta=gamma/mux
    below=k;reflection=0.;gtop=np.empty(len(t));gbottom=np.empty(len(t))
    for i in range(len(t)-1,-1,-1):
        rho=(eta[i]-below)/(eta[i]+below)
        gbottom[i]=(rho+reflection)/(1+rho*reflection)
        gtop[i]=gbottom[i]*np.exp(-2*gamma[i]*t[i])
        reflection=gtop[i];below=eta[i]
    rho=(k-below)/(k+below)
    total=(rho+reflection)/(1+rho*reflection)
    above=1+total;hx=np.empty(len(t));hz=np.empty(len(t))
    for i in range(len(t)):
        amplitude=above/(1+gtop[i])
        decay=np.exp(-gamma[i]*t[i]/2)
        reflected=gbottom[i]*np.exp(-gamma[i]*t[i])
        hx[i]=abs(incident*gamma[i]/k*amplitude*decay*(1-reflected)/(MU0*mux[i]))
        hz[i]=abs(incident*amplitude*decay*(1+reflected)/(MU0*muz[i]))
        above=amplitude*np.exp(-gamma[i]*t[i])*(1+gbottom[i])
    return float(total),hx,hz


def harmonic_fields(k, thicknesses, mux, muz, incidents):
    """Vectorized signed field amplitudes for all retained source harmonics."""
    k=np.asarray(k);incident=np.asarray(incidents)
    t=np.asarray(thicknesses);mux=np.asarray(mux);muz=np.asarray(muz)
    gamma=k[:,None]*np.sqrt(mux/muz);eta=gamma/mux
    below=k.copy();reflection=np.zeros(len(k));gtop=np.empty_like(gamma);gbottom=np.empty_like(gamma)
    for i in range(len(t)-1,-1,-1):
        rho=(eta[:,i]-below)/(eta[:,i]+below)
        gbottom[:,i]=(rho+reflection)/(1+rho*reflection)
        gtop[:,i]=gbottom[:,i]*np.exp(-2*gamma[:,i]*t[i])
        reflection=gtop[:,i];below=eta[:,i]
    rho=(k-below)/(k+below);total=(rho+reflection)/(1+rho*reflection)
    above=1+total;hx=np.empty_like(gamma);hz=np.empty_like(gamma)
    for i in range(len(t)):
        amplitude=above/(1+gtop[:,i]);decay=np.exp(-gamma[:,i]*t[i]/2)
        reflected=gbottom[:,i]*np.exp(-gamma[:,i]*t[i])
        hx[:,i]=incident*gamma[:,i]/k*amplitude*decay*(1-reflected)/(MU0*mux[i])
        hz[:,i]=incident*amplitude*decay*(1+reflected)/(MU0*muz[i])
        above=amplitude*np.exp(-gamma[:,i]*t[i])*(1+gbottom[:,i])
    return total,hx,hz


def harmonic_projection(mu_initial, bsat, hx, hz, harmonics, samples):
    theta=(np.arange(samples)+0.5)*math.pi/(2*samples)
    sine=np.sin(np.asarray(harmonics)[:,None]*theta)
    cosine=np.cos(np.asarray(harmonics)[:,None]*theta)
    x=hx.T@sine;z=hz.T@cosine
    norm=np.hypot(x,z)
    secant=1+np.minimum(mu_initial-1,bsat/np.maximum(MU0*norm,np.finfo(float).tiny))
    px=2*np.mean(secant*x*np.sin(theta),axis=1)/hx[0]
    pz=2*np.mean(secant*z*np.cos(theta),axis=1)/hz[0]
    if not np.isfinite(px).all() or not np.isfinite(pz).all() or min(px.min(),pz.min())<1-1e-10:
        raise ValueError('Harmonic closure cannot be represented by positive passive diagonal permeabilities')
    return px,pz


def source(k, harmonic, pcb=0.0008, gap=0.0005, width=0.005, height=0.003, br=1.34):
    return 2*br/(math.pi*harmonic)*math.sin(k*width/2)*(1-math.exp(-k*height))*math.exp(-k*(pcb+gap))


def solve(thickness, mu_initial, bsat, cells, samples=512,bias_harmonics=1):
    k=math.pi/0.006;incident=source(k,1)
    t=np.full(cells,thickness/cells);logx=np.full(cells,math.log(mu_initial));logz=logx.copy()
    for iteration in range(4000):
        if bias_harmonics==1:
            r,hx,hz=fields(k,t,np.exp(logx),np.exp(logz),incident)
            px,pz=projection(mu_initial,bsat,hx,hz,samples)
        else:
            harmonics=np.arange(1,2*bias_harmonics,2)
            incidents=np.array([source(k*n,int(n)) for n in harmonics])
            _,hx,hz=harmonic_fields(k*harmonics,t,np.exp(logx),np.exp(logz),incidents)
            px,pz=harmonic_projection(mu_initial,bsat,hx,hz,harmonics,samples)
        dx=np.log(px)-logx;dz=np.log(pz)-logz
        residual=float(max(np.max(abs(dx)),np.max(abs(dz))))
        if residual<1e-10:break
        # Numerical fixed-point damping, not a material or physics correction.
        logx+=0.25*dx;logz+=0.25*dz
    else:raise ValueError('Biaxial harmonic closure did not converge')
    mux,muz=np.exp(logx),np.exp(logz)
    bare=0.;image=0.;pressure=0.;fundamental_pressure=0.
    for harmonic in range(1,50,2):
        wave=k*harmonic;bn=source(wave,harmonic)
        r,_,_=fields(wave,t,mux,muz,bn)
        bare+=bn*math.exp(wave*0.0008)
        image+=r*bn*math.exp(-wave*0.0008)
        p=r*bn*bn/MU0*0.006/0.005
        pressure+=p
        if harmonic==1:fundamental_pressure=p
    return {'cells':cells,'angle_samples':samples,'bias_harmonics':bias_harmonics,'iterations':iteration+1,'closure_log_residual':residual,
            'field_ratio':1+image/bare,'pressure_pa':pressure,'fundamental_pressure_pa':fundamental_pressure,
            'mux_range':[float(mux.min()),float(mux.max())],'muz_range':[float(muz.min()),float(muz.max())]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--femm-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cells',type=int,nargs='+',default=[16,32,64])
    parser.add_argument('--angle-samples',type=int,default=512)
    parser.add_argument('--bias-harmonics',type=int,default=1,help='odd source modes included in bias, still a diagonal fundamental closure')
    args=parser.parse_args()
    if not 1<=args.bias_harmonics<=25 or args.angle_samples<128:parser.error('require 1..25 bias modes and at least 128 angle samples')
    if len(args.cells)<2 or any(n<2 for n in args.cells) or any(b<=a for a,b in zip(args.cells,args.cells[1:])):
        parser.error('require at least two increasing depth refinements')
    base=reference(args.femm_work/'v2.none.mag.out')
    report={'scope':__doc__,'status':'running','cases':{},'failures':[],
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for name,t,mu,bsat in [('flex_0.2',0.0002,130,0.25),('flex_1',0.001,130,0.25),
                           ('flex_5',0.005,130,0.25),('mnzn_2',0.002,2500,0.45)]:
        path=args.femm_work/f'v2.{name}.knee.out'
        if not path.exists():raise ValueError(f'Missing held-out material reference: {path}')
        ref=reference(path);expected_ratio=ref['mag_centre_pcb_top_By']/base['mag_centre_pcb_top_By'];expected_pressure=ref['Fy_stack']/0.01
        runs=[]
        for cells in args.cells:
            result=solve(t,mu,bsat,cells,args.angle_samples,args.bias_harmonics)
            result.update(field_ratio_error=result['field_ratio']/expected_ratio-1,pressure_error=result['pressure_pa']/expected_pressure-1)
            runs.append(result);print(name,json.dumps(result),flush=True)
        if abs(runs[-1]['field_ratio_error'])>0.05 or abs(runs[-1]['pressure_error'])>0.05:
            report['failures'].append(f'{name}: independent field/pressure discrepancy exceeds 5%')
        for a,b in zip(runs,runs[1:]):
            for key in ['field_ratio','pressure_pa']:
                if abs(a[key]/b[key]-1)>0.02:report['failures'].append(f'{name}: depth refinement {key} exceeds 2%')
        report['cases'][name]={'runs':runs,'reference_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                             'reference':{'field_ratio':expected_ratio,'pressure_pa':expected_pressure}}
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    report['status']='rejected-experiment' if report['failures'] else 'comparison-only'
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
