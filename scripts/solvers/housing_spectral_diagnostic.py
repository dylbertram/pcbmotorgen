#!/usr/bin/env python3
"""Linear planar spectral-truncation diagnostic, NOT a finite-housing solver.

Separates cross-travel cutoff, sample, depth-mesh and odd travel-harmonic
truncation. Uses the independent P1 diffusion BVP, never production reflection
recursion. Harmonic powers add only for a linear steady periodic medium after
spatial averaging. Magnetic/saturating layers are rejected, not linearized.
No fitted correction is applied to the app and no physical error bar follows.
"""
import argparse
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from check_housing_motion_reference import HOUSING, fem_mode, media
from post_project_force import sha
from source_snapshot import capture


def linear_regions(case):
    sim=case['sim'];stack=sim['backplane']
    for layer in stack['layers']:
        if layer['material']!='fr4' or layer.get('mu_r',1.) not in [None,1.]:
            raise ValueError('Diagnostic supports housing-only/FR4, not magnetic or conducting shielding')
    if not math.isfinite(case['speed_m_s']):raise ValueError('Finite speed required')
    if stack['housing']['material'] not in HOUSING:raise ValueError('Unsupported housing material')
    return media(case)


def harmonic_power(case,harmonic,cells=96,samples=1024,cutoff=15.):
    if type(harmonic) is not int or harmonic<1 or harmonic%2==0:raise ValueError('Positive odd harmonic required')
    if type(cells) is not int or cells<2 or type(samples) is not int or samples<2 or samples%2:
        raise ValueError('Positive mesh and even Simpson sample count required')
    if not math.isfinite(cutoff) or cutoff<=0:raise ValueError('Positive finite cutoff required')
    regions=linear_regions(case);sim=case['sim']
    d=sim['air_gap_m']+sim['pcb_thickness_m']
    if not math.isfinite(d) or d<=0:raise ValueError('Positive source to PCB-bottom separation required')
    k=harmonic*np.pi/sim['magnet_pitch_m'];omega=k*abs(case['speed_m_s'])
    if omega==0:return [0.]*len(regions)
    step=cutoff/d/samples;loss=np.zeros(len(regions));depth=sim['magnet_dims_m'][1]
    width,height=sim['magnet_dims_m'][0],sim['magnet_dims_m'][2]
    for i in range(samples+1):
        ky=i*step;kappa=math.hypot(k,ky)
        spectrum=depth if i==0 else 2*math.sin(ky*depth/2)/ky
        incident=2/(harmonic*np.pi)*sim['magnet_remanence_t']*math.sin(k*width/2)*(-math.expm1(-kappa*height))*math.exp(-kappa*d)
        weight=(1 if i in [0,samples] else 4 if i%2 else 2)*(incident*spectrum)**2
        values,_=fem_mode(kappa,omega,regions,cells);loss+=weight*values
    return (loss*(sim['magnet_count']*sim['magnet_pitch_m']*step/(6*np.pi))).tolist()


def rel(a,b):
    return float(np.max(abs(np.asarray(a)-b)/np.maximum(abs(np.asarray(b)),1e-12)))


def diagnose(case):
    # Isolate each refinement axis; use the finest combination for the
    # harmonic series, never adjust physical parameters to improve agreement.
    mesh_coarse=harmonic_power(case,1,cells=96,samples=2048,cutoff=30.)
    mesh_fine=harmonic_power(case,1,cells=192,samples=2048,cutoff=30.)
    sample_coarse=harmonic_power(case,1,cells=192,samples=1024,cutoff=30.)
    cutoffs={str(c):harmonic_power(case,1,cells=192,samples=int(2048*c/30),cutoff=c) for c in [15.,22.5,30.]}
    fundamental=cutoffs['30.0'];terms={'1':fundamental};totals={'1':fundamental};total=np.asarray(fundamental)
    coarse_mesh_total=np.asarray(mesh_coarse);coarse_sample_total=np.asarray(sample_coarse)
    for odd in range(3,16,2):
        value=harmonic_power(case,odd,cells=192,samples=2048,cutoff=30.)
        terms[str(odd)]=value;total=total+value;totals[str(odd)]=total.tolist()
        coarse_mesh_total+=harmonic_power(case,odd,cells=96,samples=2048,cutoff=30.)
        coarse_sample_total+=harmonic_power(case,odd,cells=192,samples=1024,cutoff=30.)
    mesh_error=rel(mesh_coarse,mesh_fine);samples_error=rel(sample_coarse,mesh_fine)
    cutoff_error=rel(cutoffs['15.0'],fundamental)
    last_change=rel(totals['11'],totals['15'])
    aggregate_mesh_error=rel(coarse_mesh_total,total);aggregate_sample_error=rel(coarse_sample_total,total)
    return {'scope':__doc__,'fundamental_region_powers_w':fundamental,'harmonic_region_powers_w':terms,
        'cumulative_region_powers_w':totals,'cross_travel_cutoff_region_powers_w':cutoffs,
        'depth_mesh_relative_change':mesh_error,'sample_relative_change':samples_error,
        'cutoff15_to30_relative_change':cutoff_error,'harmonics11_to15_relative_change':last_change,
        'aggregate_depth_mesh_relative_change':aggregate_mesh_error,'aggregate_sample_relative_change':aggregate_sample_error,
        'harmonics15_over_fundamental_housing_power':float(total[-1]/max(fundamental[-1],1e-12)),
        'numerical_controls_passed':bool(max(mesh_error,samples_error,last_change,aggregate_mesh_error,aggregate_sample_error)<=.02),
        'production_cutoff_check_passed':bool(cutoff_error<=.02)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,action='append',required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    if args.work.exists():parser.error('Preserve previous spectral evidence')
    args.work.mkdir(parents=True);started=time.monotonic()
    report={'status':'running','scope':__doc__,'cases':{},'failures':[],
        'source_snapshots':capture(args.work,[Path(__file__),Path(__file__).with_name('check_housing_motion_reference.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(args.work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for path in args.case:
            digest=sha(path);case=json.loads(path.read_text());value=diagnose(case)
            if sha(path)!=digest:raise ValueError('Physical input changed during diagnostic')
            report['cases'][str(path.resolve())]={'input_sha256':digest,**value}
            if not value['numerical_controls_passed'] or not value['production_cutoff_check_passed']:report['failures'].append(str(path))
            save();print(path.name,value['harmonics15_over_fundamental_housing_power'],flush=True)
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Diagnostic source changed')
        report.update(status='completed-linear-spectral-diagnostic-only' if not report['failures'] else 'failed-spectral-controls',seconds=time.monotonic()-started);save()
        if report['failures']:raise ValueError('Spectral controls failed; no corrected app estimate accepted')
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
