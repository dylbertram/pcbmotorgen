#!/usr/bin/env python3
"""Independent complex P1 diffusion FEM check of planar housing motion.

This solves a scalar TE diffusion boundary-value problem separately for each
cross-travel wavenumber, with material interfaces and Robin air boundaries.
It does not reuse the Rust reflection or face-amplitude recursion. This is
independent numerical verification of the declared periodic-planar model, NOT
finite-housing, entry/exit, thermal, nonlinear moving-material or hardware
validation. Magnetic reference cases deliberately use weak PM bias so the
declared material curves remain in their linear region without fitting mu.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import time
import platform
from importlib.metadata import version

import numpy as np
from scipy.linalg import solve_banded

from post_project_force import sha
from source_snapshot import capture

MU0=4e-7*np.pi
HOUSING={'aluminum6061':(1.,25e6),'aluminum5052':(1.,20e6),'stainless304':(1.02,1.39e6),'stainless316':(1.02,1.35e6)}
LAYERS={'fr4':(1.,0.),'flex_ferrite':(130.,0.),'ni_zn_ferrite':(500.,0.),'mn_zn_ferrite':(2500.,.2),'silicon_steel':(4000.,2e6)}


def case_base():
    return {'sim':{'magnet_dims_m':[.005,.005,.003],'magnet_count':5,'magnet_pitch_m':.006,'magnet_remanence_t':1.34,
        'active_area_length_m':.195,'board_width_m':.02,'pcb_thickness_m':.0008,'air_gap_m':.0005,
        'strands_per_phase':1,'phases':3,'spacing_ratio':1.,'max_current_a':1.,'supply_voltage_v':12.,
        'min_trace_m':.0002,'min_space_m':.000127,'min_via_drill_m':.0003,'min_via_annular_ring_m':.0001,
        'max_layers':16,'num_layers':2,'drive_frequency_hz':500.,'max_temperature_rise_c':20.,
        'target_force_n':.5,'peak_force_n':1.,'friction_n':.05,'carriage_mass_kg':.015,'max_accel_m_s2':2.,'capacitor_bank_uf':1000.,
        'backplane':{'layers':[],'housing':{'material':'aluminum6061','thickness_m':.001,'gap_m':.0001}}},
        'speed_m_s':20.,'duration_s':.1}


def cases():
    result=[]
    for material in HOUSING:
        for speed in [.001,20.]:
            case=case_base();case['sim']['backplane']['housing']['material']=material;case['speed_m_s']=speed
            result.append((material+'-'+str(speed),case))
    case=case_base();case['sim'].update(magnet_count=12,num_layers=16,magnet_dims_m=[.008,.012,.004],magnet_pitch_m=.01,pcb_thickness_m=.002)
    case['sim']['backplane']['housing'].update(material='stainless316',thickness_m=.005,gap_m=.01);case['speed_m_s']=-20.
    result.append(('max-count-wall-gap-reverse',case))
    case=case_base();case['sim'].update(magnet_count=2,num_layers=4,magnet_dims_m=[.004,.007,.002],magnet_pitch_m=.005)
    case['sim']['backplane']['housing'].update(material='aluminum5052',thickness_m=.005,gap_m=0.)
    result.append(('short-array-thick-wall',case))
    case=case_base();case['sim']['magnet_remanence_t']=.001
    case['sim']['backplane']['layers']=[{'material':'silicon_steel','thickness_m':.00035}]
    result.append(('weak-bias-conducting-shield-partition',case))
    case=case_base();case['sim'].update(magnet_count=12,num_layers=16,magnet_remanence_t=.001)
    case['sim']['backplane']['layers']=[{'material':'ni_zn_ferrite','thickness_m':.002},{'material':'fr4','thickness_m':.002},{'material':'mn_zn_ferrite','thickness_m':.002}]
    case['sim']['backplane']['housing'].update(thickness_m=.005,gap_m=.01)
    result.append(('three-layers-two-mm-each',case))
    return result


def media(case):
    stack=case['sim']['backplane'];result=[]
    for layer in stack['layers']:
        mu,sigma=LAYERS[layer['material']];result.append((layer.get('mu_r') or mu,sigma,layer['thickness_m']))
    result.append((1.,0.,stack['housing']['gap_m']))
    mu,sigma=HOUSING[stack['housing']['material']];result.append((mu,sigma,stack['housing']['thickness_m']))
    return result


def fem_mode(kappa,omega,regions,cells):
    lengths=[];mus=[];sigmas=[];owners=[]
    for index,(mu,sigma,thickness) in enumerate(regions):
        if thickness==0:continue
        lengths.extend([thickness/cells]*cells);mus.extend([mu]*cells);sigmas.extend([sigma]*cells);owners.extend([index]*cells)
    h=np.asarray(lengths);mu=np.asarray(mus);sigma=np.asarray(sigmas);count=len(h)
    stiffness=1/(mu*h);mass=(kappa*kappa/mu+1j*omega*MU0*sigma)*h/6
    diagonal=np.zeros(count+1,dtype=complex);diagonal[:-1]+=stiffness+2*mass;diagonal[1:]+=stiffness+2*mass
    diagonal[0]+=kappa;diagonal[-1]+=kappa;off=-stiffness+mass
    band=np.zeros((3,count+1),dtype=complex);band[1]=diagonal;band[0,1:]=off;band[2,:-1]=off
    rhs=np.zeros(count+1,dtype=complex);rhs[0]=2*kappa
    potential=solve_banded((1,1),band,rhs)
    # Exact consistent P1 mass integral of |A|² on each cell.
    squared=h/3*(abs(potential[:-1])**2+abs(potential[1:])**2+np.real(potential[:-1]*potential[1:].conj()))
    cell_loss=sigma*(omega/kappa)**2*squared
    losses=np.bincount(owners,weights=cell_loss,minlength=len(regions))
    work=-2*omega/(kappa*MU0)*potential[0].imag
    return losses,work


def reference(case,cells,samples=512):
    sim=case['sim'];regions=media(case);k=np.pi/sim['magnet_pitch_m'];omega=k*abs(case['speed_m_s'])
    if omega==0:return {'regions_w':[0.]*len(regions),'mechanical_power_w':0.,'balance':0.}
    depth=sim['magnet_dims_m'][1];height=sim['magnet_dims_m'][2];width=sim['magnet_dims_m'][0]
    d=sim['air_gap_m']+sim['pcb_thickness_m'];step=15/d/samples;loss=np.zeros(len(regions));work=0.
    for i in range(samples+1):
        ky=i*step;kappa=math.hypot(k,ky);spectrum=depth if i==0 else 2*math.sin(ky*depth/2)/ky
        incident=2/np.pi*sim['magnet_remanence_t']*math.sin(k*width/2)*(1-math.exp(-kappa*height))*math.exp(-kappa*d)
        weight=(1 if i in [0,samples] else (4 if i%2 else 2))*(incident*spectrum)**2
        values,boundary=fem_mode(kappa,omega,regions,cells);loss+=weight*values;work+=weight*boundary
    scale=sim['magnet_count']*sim['magnet_pitch_m']*step/(6*np.pi);loss*=scale;work*=scale
    return {'regions_w':loss.tolist(),'mechanical_power_w':float(work),'balance':abs(float(loss.sum())-work)/max(abs(work),float(loss.sum()),1e-12)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();binary=args.binary.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous independent comparisons')
    work.mkdir(parents=True);started=time.monotonic();root=Path(__file__).resolve().parents[2]
    output={'status':'running','scope':__doc__,'binary_sha256':sha(binary),'cases':{},'failures':[],
        'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':version('scipy')},
        'source_snapshots':capture(work,[Path(__file__),*[root/p for p in [
            'Cargo.toml','Cargo.lock','crates/pcbmotorgen-simulation/src/backplane/housing_motion.rs',
            'crates/pcbmotorgen-simulation/src/backplane/mod.rs','crates/pcbmotorgen-simulation/src/drive/mod.rs',
            'crates/pcbmotorgen-simulation/examples/housing_motion_dump.rs']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for name,case in cases():
            case_path=work/(name+'.input.json');case_path.write_text(json.dumps(case,indent=2)+'\n')
            run=subprocess.run([str(binary),str(case_path)],capture_output=True,text=True,timeout=60)
            (work/(name+'.stdout.json')).write_text(run.stdout);(work/(name+'.stderr.log')).write_text(run.stderr)
            if run.returncode:raise ValueError(name+': Rust calculation unavailable/failed')
            rust=json.loads(run.stdout)
            if rust['status']!='experimental':raise ValueError(name+': no experimental estimate')
            levels={};previous=None;converged=False
            for cells in [24,48,96,192]:
                value=reference(case,cells);levels[str(cells)]=value
                if previous:
                    a=np.asarray(previous['regions_w']);b=np.asarray(value['regions_w'])
                    change=float(np.max(abs(a-b)/np.maximum(abs(b),1e-12)))
                    levels[str(cells)]['refinement_relative_change']=change
                    if change<=.02:converged=True;break
                previous=value
            expected=np.asarray(value['regions_w']);actual=np.array([*rust['estimate']['layer_joule_power_w'],0.,rust['estimate']['housing_joule_power_w']])
            error=float(np.max(abs(actual-expected)/np.maximum(abs(expected),1e-12)))
            passed=bool(converged and value['balance']<=1e-8 and error<=.05)
            output['cases'][name]={'input_sha256':sha(case_path),'rust':rust,'independent_fem':levels,'maximum_region_relative_difference':error,'passed':passed}
            if not passed:output['failures'].append(name)
            save();print(name,'region agreement',error,'passed',passed,flush=True)
        if sha(binary)!=output['binary_sha256']:raise ValueError('Rust executable changed during independent audit')
        for path,entry in output['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Housing motion source changed during audit')
        output.update(status='failed' if output['failures'] else 'passed-independent-planar-housing-motion-only',seconds=time.monotonic()-started);save()
        if output['failures']:raise ValueError('Independent housing motion cases failed')
    except BaseException as error:
        output.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
