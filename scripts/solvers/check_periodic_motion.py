#!/usr/bin/env python3
"""Independent resolution studies of a nonlinear periodic moving-PM prototype.

Not a finite-array operating prediction. Purely periodic infinite cross-depth
current sheets cannot establish finite housing edges, slots or current closure.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from periodic_motion import run
from source_snapshot import capture


def compare(first,second):
    changes={key:abs(first[key]/second[key]-1) for key in ['joule_w_m2','magnet_force_density_n_m2']}
    if not np.isfinite(list(changes.values())).all():raise ValueError('Nonfinite motion refinement')
    return {'relative_changes':changes,'passed':max(changes.values())<=0.02}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--thickness-mm',type=float,default=0.2)
    parser.add_argument('--steps-per-period',type=int,default=256)
    parser.add_argument('--periods',type=int,default=8)
    parser.add_argument('--require-knee-crossing',action='store_true')
    args=parser.parse_args()
    if not np.isfinite(args.thickness_mm) or args.thickness_mm<=0:parser.error('positive finite thickness required')
    if args.steps_per_period<256 or args.periods<4:parser.error('at least 256 steps per period and four periods required')
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):parser.error('preserve prior trials; use an empty work directory')
    report={'scope':__doc__,'status':'running','material':{'thickness_m':args.thickness_mm*1e-3,'mu_initial':130.,'bsat_t':0.25},
            'runs':{},'refinements':{},'failures':[]}
    report['source_snapshots']=capture(work,[Path(__file__),*[Path(__file__).parent/name for name in
        ['periodic_motion.py','spectral_transient.py','spectral_biased_ac.py','spectral_incremental.py','spectral_plate.py','vector_harmonic_screen.py']]])
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    controls={'cells':8,'modes':3,'samples':128,'steps_per_period':args.steps_per_period,'periods':args.periods,'wall_cells':16,'gap_cells':4}
    levels=[('base',{}),('time',{'steps_per_period':2*args.steps_per_period}),('depth',{'cells':16}),('modes',{'modes':5}),
            ('angles',{'samples':256}),('wall',{'wall_cells':32}),('gap',{'gap_cells':8})]
    previous=None
    for name,update in levels:
        controls.update(update)
        result=run(20,thickness=args.thickness_mm*1e-3,trace_path=work/f'{name}-trace.npz',**controls)
        report['runs'][name]=result
        if previous:
            check=compare(report['runs'][previous],result);report['refinements'][name]=check
            if not check['passed']:report['failures'].append(f'{previous}->{name} refinement exceeds 2%')
        previous=name;save();print(name,'loss',result['joule_w_m2'],'force density',result['magnet_force_density_n_m2'],flush=True)
    for name,speed in [('zero',0),('reverse',-20),('slow',2)]:
        result=run(speed,thickness=args.thickness_mm*1e-3,trace_path=work/f'{name}-trace.npz',**controls);report['runs'][name]=result;save()
        print(name,'loss',result['joule_w_m2'],'force density',result['magnet_force_density_n_m2'],flush=True)
    forward=report['runs']['gap'];reverse=report['runs']['reverse']
    errors={'loss':abs(forward['joule_w_m2']/reverse['joule_w_m2']-1),
            'force_reversal':abs(forward['magnet_force_density_n_m2']/reverse['magnet_force_density_n_m2']+1)}
    report['reverse_errors']=errors
    if max(errors.values())>0.02:report['failures'].append('Reverse-velocity symmetry exceeds 2%')
    crossing=forward['sampled_material_state']['quadrature_fraction_crossing_knee']
    report['sampled_knee_crossing_observed']=crossing>0
    if args.require_knee_crossing and crossing<=0:report['failures'].append('No sampled knee crossing was observed in the moving plate')
    report['status']='failed' if report['failures'] else 'passed-periodic-nonlinear-motion-numerics-only';save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
