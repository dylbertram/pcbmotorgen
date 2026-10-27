#!/usr/bin/env python3
"""Independent DC differential-inductance check against matched-knee FEMM.

The PM bias is static. FEMM uses its previous-solution differential tensor, not
an oscillating PM source. Compare two source phases and two isolated sheets.
This does not qualify frequency-dependent eddy impedance, PWM or finite arrays.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from spectral_incremental import response
import femm_backplane as femm
from source_snapshot import capture


def factor_errors(actual,expected,relative=0.05):
    actual=np.asarray(actual);expected=np.asarray(expected)
    if actual.shape!=(2,) or expected.shape!=(2,) or not np.isfinite(actual).all() or not np.isfinite(expected).all() or np.any(expected<=0):
        raise ValueError('Invalid independent incremental inductance')
    return abs(actual-expected),np.maximum(1e-3,relative*abs(expected-1))


def knee_points(mu,bsat,digits):
    points=femm.bh_points(mu,bsat,knee=True)
    if not digits:return points
    if mu<=1 or bsat<=0 or digits not in [4,6]:raise ValueError('Invalid knee-table refinement')
    bk=bsat*mu/(mu-1)
    for exponent in range(2,digits+1):
        for sign in [-1,1]:
            b=bk+sign*bsat*10**(-exponent)
            h=b/(femm.MU0*mu) if b<=bk else (b-bsat)/femm.MU0
            points.append((b,h))
    return sorted(set(points),key=lambda pair:pair[1])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--run-femm',action='store_true')
    parser.add_argument('--femm-work',type=Path,help='reuse identical archived FEMM cases in this directory')
    parser.add_argument('--case',nargs='+',choices=['flex_0.2','flex_1','mnzn_2'])
    parser.add_argument('--quick',action='store_true',help='setup comparison only, no separate refinement gates')
    parser.add_argument('--knee-density',type=int,choices=[0,4,6],default=0,help='add exact B-H samples within 1e-4 or 1e-6 of the knee, without changing its law')
    parser.add_argument('--source-strips',type=int,default=96,help='independently refine the sinusoidal FEMM source representation')
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    femm_work=args.femm_work.resolve() if args.femm_work else work
    femm_work.mkdir(parents=True,exist_ok=True)
    if (work/'summary.json').exists():parser.error('preserve the previous report; choose a new work directory')
    if not 24<=args.source_strips<=768 or args.source_strips%2:parser.error('source strips must be even, between 24 and 768')
    femm.set_pcb(0.8);ys=femm.sheet_ys(2);segments=args.source_strips
    source_prefix='inc-knee' if segments==96 else f'inc-knee-n{segments}'
    report={'scope':__doc__,'status':'running','cases':{},'failures':[],'source_strip_count':segments,
            'knee_table_density':args.knee_density,
            'refined':not args.quick,
            'phase_convention':'model x = FEMM x + tau/2; FEMM phase 0 uses model sine A, phase pi/2 cosine A',
            'femm_work':str(femm_work),
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'incremental_kernel_sha256':hashlib.sha256((Path(__file__).parent/'spectral_incremental.py').read_bytes()).hexdigest(),
            'static_kernel_sha256':hashlib.sha256((Path(__file__).parent/'spectral_plate.py').read_bytes()).hexdigest()}
    report['source_snapshots']=capture(work,[Path(__file__),Path(__file__).parent/'spectral_incremental.py',
                                            Path(__file__).parent/'spectral_plate.py',Path(femm.__file__),
                                            Path(__file__).parent/'vector_harmonic_screen.py'])
    output=work/'summary.json';output.write_text(json.dumps(report,indent=2)+'\n')
    bases={};hashes={}

    def run_case(case):
        name=case['name']
        if args.run_femm:femm.run_femm(case,str(femm_work))
        path=femm_work/(name+'.out')
        result=femm.cached_femm_result(case,str(femm_work))
        hashes[name]={'output':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'input':hashlib.sha256((femm_work/(name+'.case.lua')).read_bytes()).hexdigest()}
        return result

    for label,t,mu,bsat in [('flex_0.2',0.0002,130,0.25),('flex_1',0.001,130,0.25),('mnzn_2',0.002,2500,0.45)]:
        if args.case and label not in args.case:continue
        runs={}
        levels=[('base',32,9,512)] if args.quick else [('base',32,9,512),('depth',64,9,512),('modes',64,17,512),('angles',64,17,1024)]
        for tag,cells,modes,angles in levels:
            result=response(t,mu,bsat,cells,modes,angles)
            runs[tag]=result
            report['cases'][label]={'spectral':runs};output.write_text(json.dumps(report,indent=2)+'\n')
            print(label,tag,'reflection',result['fundamental_reflection_per_phase'],'coil factors',result['coil_factors_per_phase'],flush=True)
        stack={'layers':[{'material':'mn_zn_ferrite' if label=='mnzn_2' else 'flex_ferrite','thickness_m':t}], 'housing':None}
        prefix=source_prefix if not args.knee_density else f'{source_prefix}-b{args.knee_density}'
        def refined_curve(case):
            if args.knee_density:
                for material in case['materials']:
                    if 'bh' in material:material['bh']=knee_points(mu,bsat,args.knee_density)
            return case
        bias=refined_curve(femm.build_case(f'{prefix}.{label}.bias',stack,(True,*femm.sheet_rects(ys,n=segments,live=())),nonlinear='knee'))
        run_case(bias)
        factors=[]
        for phase,angle in enumerate([0,math.pi/2]):
            if phase not in bases:
                bases[phase]=sum(run_case(femm.build_case(f'{source_prefix}.none.p{phase}.{s}',femm.NONE,
                                     (False,*femm.sheet_rects(ys,n=segments,phase=angle,live=(s,)))))['AJ_sources_re'] for s in range(2))
            value=0.
            for sheet in range(2):
                case=refined_curve(femm.build_case(f'{prefix}.{label}.p{phase}.{sheet}',stack,
                                    (False,*femm.sheet_rects(ys,n=segments,phase=angle,live=(sheet,))),
                                    nonlinear='knee',previous=bias['name']))
                case['previous_text']=femm.hash_text(femm.lua(bias))
                value+=run_case(case)['AJ_sources_re']
            factors.append(value/bases[phase])
        actual=np.asarray(runs[levels[-1][0]]['coil_factors_per_phase']);expected=np.asarray(factors)
        difference,tolerance=factor_errors(actual,expected)
        # Absolute floor prevents a near-unity factor from either hiding a
        # material-effect error or demanding a meaningless relative zero test.
        if np.any(difference>tolerance):report['failures'].append(f'{label}: added-inductance agreement exceeds max(0.001, 5% of added factor)')
        if not args.quick:
            for first,second in [('base','depth'),('depth','modes'),('modes','angles')]:
                a=np.asarray(runs[first]['coil_factors_per_phase']);b=np.asarray(runs[second]['coil_factors_per_phase'])
                change,limit=factor_errors(a,b,relative=0.02)
                if np.any(change>limit):report['failures'].append(f'{label}: {first}->{second} added factor changes beyond max(0.001, 2%)')
        report['cases'][label]={'spectral':runs,'femm_coil_factors_per_phase':factors,
                                'absolute_factor_error':difference.tolist(),'factor_error_tolerance':tolerance.tolist()}
        report['femm_sha256']=hashes;output.write_text(json.dumps(report,indent=2)+'\n')
        print(label,'FEMM factors',factors,'absolute error',difference.tolist(),flush=True)
    report['status']='failed' if report['failures'] else 'comparison-only'
    output.write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
