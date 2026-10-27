#!/usr/bin/env python3
"""Offline periodic nonlinear time/linearization study, not finite motion.

First independently refine time at a small perturbation, then increase source
amplitude without promising that the linearized prediction remains valid.
No material law, nonlinear tolerance or acceptance gate is tuned to the data.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from source_snapshot import capture
from spectral_transient import run


def compare(first,second,relative):
    a=np.asarray(first['reflection']);b=np.asarray(second['reflection'])
    limits=np.maximum([1e-3,1e-5],relative*abs(b));error=abs(a-b)
    power=abs(first['joule_coefficient_w_m2_t2']/second['joule_coefficient_w_m2_t2']-1)
    return {'reflection_absolute_change':error.tolist(),'reflection_limits':limits.tolist(),
            'loss_relative_change':power,'passed':bool(np.all(error<=limits) and power<=relative)}


def linearization(result):
    a=np.asarray(result['reflection']);b=np.asarray(result['linearized_reflection'])
    limits=np.maximum([1e-3,1e-5],0.05*abs(b));difference=abs(a-b)
    power=abs(result['joule_coefficient_w_m2_t2']/result['linearized_joule_coefficient_w_m2_t2']-1)
    return {'reflection_absolute_error':difference.tolist(),'reflection_limits':limits.tolist(),
            'loss_relative_error':power,'within_five_percent':bool(np.all(difference<=limits) and power<=0.05)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--thickness-mm',type=float,default=0.2)
    parser.add_argument('--cells',type=int,default=8)
    parser.add_argument('--modes',type=int,default=3)
    parser.add_argument('--samples',type=int,default=128)
    parser.add_argument('--wall-cells',type=int,default=16)
    parser.add_argument('--periods',type=int,default=32)
    parser.add_argument('--phase',type=int,nargs='+',choices=[0,1],default=[0,1])
    parser.add_argument('--fractions',type=float,nargs='+',default=[1e-4,1e-3,0.01,0.1])
    args=parser.parse_args()
    if not np.isfinite([args.thickness_mm,*args.fractions]).all() or args.thickness_mm<=0 or min(args.fractions)<=0:parser.error('positive finite thickness/amplitudes required')
    if len(set(args.phase))!=len(args.phase) or len(set(args.fractions))!=len(args.fractions):parser.error('duplicate phase/amplitude')
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):parser.error('preserve earlier studies; choose an empty directory')
    report={'scope':__doc__,'status':'running','material':{'thickness_m':args.thickness_mm*1e-3,'mu':130.,'bsat_t':0.25},
            'phases':{},'failures':[],'frequency_hz':100000.}
    report['source_snapshots']=capture(work,[Path(__file__),*[Path(__file__).parent/name for name in
        ['spectral_transient.py','spectral_biased_ac.py','spectral_incremental.py','spectral_plate.py','vector_harmonic_screen.py']]])
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    for phase in args.phase:
        trials={};report['phases'][str(phase)]={'trials':trials,'time_refinements':{}};save()
        previous=None
        for steps in [64,128,256]:
            result=run(args.thickness_mm*1e-3,130.,0.25,fraction=1e-3,phase=phase,cells=args.cells,modes=args.modes,
                       samples=args.samples,steps_per_period=steps,periods=args.periods,wall_cells=args.wall_cells)
            trials[str(steps)]=result
            if previous:
                check=compare(previous,result,0.02);report['phases'][str(phase)]['time_refinements'][str(steps)]=check
                if not check['passed']:report['failures'].append(f'phase {phase}: independent time refinement failed at {steps}')
            previous=result;save();print('phase',phase,'time',steps,'linearization',linearization(result),flush=True)
        if not linearization(trials['256'])['within_five_percent']:
            report['failures'].append(f'phase {phase}: refined small-amplitude tensor limit failed')
        amplitudes={};report['phases'][str(phase)]['amplitudes']=amplitudes
        for fraction in args.fractions:
            if fraction==1e-3:result=trials['256']
            else:result=run(args.thickness_mm*1e-3,130.,0.25,fraction=fraction,phase=phase,cells=args.cells,modes=args.modes,
                           samples=args.samples,steps_per_period=256,periods=args.periods,wall_cells=args.wall_cells)
            check=linearization(result);amplitudes[str(fraction)]={'result':result,'linearization':check}
            if fraction<=1e-3 and not check['within_five_percent']:report['failures'].append(f'phase {phase}: small-amplitude tensor limit failed at {fraction}')
            save();print('phase',phase,'fraction',fraction,check,flush=True)
    report['status']='failed' if report['failures'] else 'passed-periodic-time-and-small-signal-only';save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
