#!/usr/bin/env python3
"""Pilot of DC-bias differential-tensor transfer into a complex planar solve.

Uses a static PM bias, matched-knee FEMM previous-solution AC, finite Al wall,
two isolated coil sheets and two spatial phases. Does not qualify nonlinear
transients, large ripple, finite current closure, arbitrary PWM or hardware.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from spectral_biased_ac import bias_state, complex_response
from check_spectral_incremental import knee_points, factor_errors
from source_snapshot import capture
import femm_backplane as femm


def geometry_hash(case):
    data={key:case[key] for key in ['period','bands','rects','labels']}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def refined_mesh(case,scale):
    # build_case can share source rectangles with another case. Never modify
    # those objects in place, or bare then stack receives scale squared.
    case=copy.deepcopy(case)
    for kind in ['bands','rects','labels']:
        for region in case[kind]:
            if region.get('mesh',0)>0:region['mesh']*=scale
    return case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--run-femm',action='store_true')
    parser.add_argument('--femm-work',type=Path,help='reuse identical archived FEMM cases here')
    parser.add_argument('--case',choices=['flex_0.2','flex_1','mnzn_2'],default='flex_0.2')
    parser.add_argument('--frequency',type=float,default=100e3)
    parser.add_argument('--knee-density',type=int,choices=[0,4,6],default=0)
    parser.add_argument('--cells',type=int,default=32)
    parser.add_argument('--modes',type=int,default=9)
    parser.add_argument('--samples',type=int,default=512)
    parser.add_argument('--wall-cells',type=int,default=32)
    parser.add_argument('--gap-cells',type=int,default=4)
    parser.add_argument('--source-strips',type=int,default=96)
    parser.add_argument('--mesh-scale',type=float,default=1.)
    parser.add_argument('--far-scale',type=float,default=1.)
    args=parser.parse_args()
    if not np.isfinite(args.frequency) or args.frequency<=0:parser.error('positive finite frequency required')
    if not 24<=args.source_strips<=768 or args.source_strips%2:parser.error('even source strip count between 24 and 768 required')
    if not np.isfinite([args.mesh_scale,args.far_scale]).all() or min(args.mesh_scale,args.far_scale)<=0:parser.error('positive finite mesh/far scales required')
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    femm_work=args.femm_work.resolve() if args.femm_work else work
    femm_work.mkdir(parents=True,exist_ok=True)
    if (work/'summary.json').exists():parser.error('preserve the previous job; use a new directory')
    materials={'flex_0.2':(0.0002,130,0.25,0.),'flex_1':(0.001,130,0.25,0.),'mnzn_2':(0.002,2500,0.45,0.2)}
    t,mu,bsat,layer_sigma=materials[args.case]
    report={'scope':__doc__,'status':'running','case':args.case,'frequency_hz':args.frequency,'knee_density':args.knee_density,
            'femm_work':str(femm_work),'source_strip_count':args.source_strips,
            'femm_mesh_scale':args.mesh_scale,'femm_far_scale':args.far_scale,
            'resolution':{'layer_cells':args.cells,'modes_per_phase':args.modes,'angle_samples':args.samples,'wall_cells':args.wall_cells,'gap_cells':args.gap_cells},
            'material':{'thickness_m':t,'mu_initial':mu,'saturation_polarization_t':bsat},'failures':[]}
    report['source_snapshots']=capture(work,[Path(__file__),Path(__file__).parent/'spectral_biased_ac.py',
        Path(__file__).parent/'spectral_incremental.py',Path(__file__).parent/'spectral_plate.py',Path(femm.__file__),
        Path(__file__).parent/'check_spectral_incremental.py',Path(__file__).parent/'vector_harmonic_screen.py'])
    output=work/'summary.json';output.write_text(json.dumps(report,indent=2)+'\n')
    full,hessian,proof=bias_state(t,mu,bsat,args.cells,args.modes,args.samples)
    result=complex_response(full,hessian,args.frequency,wall_cells=args.wall_cells,gap_cells=args.gap_cells,layer_conductivity=layer_sigma)
    report.update(bias_convergence=proof,spectral=result)
    output.write_text(json.dumps(report,indent=2)+'\n')
    femm.set_pcb(0.8);femm.FAR*=args.far_scale
    ys=femm.sheet_ys(2);segments=args.source_strips
    housing=femm.housing('aluminum6061',1.0,0.1)
    stack={'layers':[{'material':'mn_zn_ferrite' if args.case=='mnzn_2' else 'flex_ferrite','thickness_m':t}], 'housing':housing}
    def curve(case):
        if args.knee_density:
            for mat in case['materials']:
                if 'bh' in mat:mat['bh']=knee_points(mu,bsat,args.knee_density)
        return case
    def mesh(case):
        return refined_mesh(case,args.mesh_scale)
    # Build the bias with the AC geometry/skin bands, then turn frequency off.
    # Conductivity has no DC effect, while the previous-solution mesh must match.
    bias=mesh(curve(femm.build_case('biased-ac.bias',stack,(True,*femm.sheet_rects(ys,n=segments,live=())),freq=args.frequency,nonlinear='knee')))
    bias['freq']=0
    hashes={}
    def run_case(case):
        if args.run_femm:femm.run_femm(case,str(femm_work))
        path=femm_work/(case['name']+'.out')
        hashes[case['name']]={'input':hashlib.sha256((femm_work/(case['name']+'.case.lua')).read_bytes()).hexdigest(),
                             'output':hashlib.sha256(path.read_bytes()).hexdigest()}
        return femm.cached_femm_result(case,str(femm_work))
    run_case(bias);factors=[];losses=[];source_work=[]
    for phase,angle in enumerate([0,math.pi/2]):
        base=0j;value=0j;power=0.
        for sheet in range(2):
            source=(False,*femm.sheet_rects(ys,n=segments,phase=angle,live=(sheet,)))
            bare=run_case(mesh(femm.build_case(f'biased-ac.none.p{phase}.{sheet}',femm.NONE,source,freq=args.frequency)))
            base+=complex(bare['AJ_sources_re'],bare['AJ_sources_im'])
            case=mesh(curve(femm.build_case(f'biased-ac.stack.p{phase}.{sheet}',stack,source,freq=args.frequency,nonlinear='knee',previous=bias['name'])))
            case['previous_text']=femm.hash_text(femm.lua(bias))
            if geometry_hash(case)!=geometry_hash(bias):raise ValueError('AC and bias meshes describe different geometry')
            actual=run_case(case)
            value+=complex(actual['AJ_sources_re'],actual['AJ_sources_im']);power+=actual['loss_stack']
        factors.append(value/base);losses.append(power);source_work.append(-math.pi*args.frequency*value.imag)
    factors=np.asarray(factors);losses=np.asarray(losses);source_work=np.asarray(source_work)
    actual=np.array([complex(*v) for v in result['coil_factors_per_phase']])
    real_error,real_limit=factor_errors(actual.real,factors.real)
    imag_error=abs(actual.imag-factors.imag);imag_limit=np.maximum(1e-5,0.05*abs(factors.imag))
    if np.any(real_error>real_limit):report['failures'].append('Added reactive factor differs by more than max(0.001, 5%)')
    if np.any(imag_error>imag_limit):report['failures'].append('Added resistive factor differs by more than max(1e-5, 5%)')
    if np.any(losses<=0) or np.any(abs(source_work/losses-1)>0.02):report['failures'].append('Independent FEMM source-work/Joule balance exceeds 2%')
    # Fundamental coefficient of the actual 80%-duty strip source, with exact
    # finite-thickness exponential weighting. Higher strip aliases are omitted
    # by this normalization and remain part of the comparison uncertainty.
    k=math.pi/0.006;segment=0.012/segments;coefficient=0.8*np.sinc(k*0.4*segment/math.pi)
    sheet_t=0.00002
    incident=femm.MU0*1e6*sheet_t*coefficient/2*np.exp(-k*np.asarray(ys)*1e-3)*math.sinh(k*sheet_t/2)/(k*sheet_t/2)
    predicted_loss=np.asarray(result['joule_coefficient_w_m2_t2'])*float(np.sum(incident**2))*0.012
    if np.any(abs(predicted_loss/losses-1)>0.05):report['failures'].append('Independent Joule-loss normalization differs by more than 5%')
    report.update(status='failed' if report['failures'] else 'comparison-only',
                  femm_factors=[[float(v.real),float(v.imag)] for v in factors],femm_loss_w=losses.tolist(),
                  femm_source_work_w=source_work.tolist(),spectral_loss_w=predicted_loss.tolist(),femm_sha256=hashes,
                  real_factor_error=real_error.tolist(),imaginary_factor_error=imag_error.tolist())
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
