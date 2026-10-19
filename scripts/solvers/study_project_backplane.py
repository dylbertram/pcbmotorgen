#!/usr/bin/env python3
"""Read-only thickness study for a saved project's single magnetic backplane.

Outputs a periodic/infinite-cross-depth static reference and two DC differential
coil alignments. Numerical convergence is not independent validation of every
user material. No finite-array force, coverage-weighted winding inductance,
housing drag, PWM limit or bearing-load recommendation is produced.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from check_project_spectral import inputs
from spectral_plate import solve
from spectral_incremental import response
from source_snapshot import capture
import femm_backplane as femm


def refinement_errors(first,second):
    errors={key:abs(first['static'][key]/second['static'][key]-1) for key in ['field_ratio','pressure_pa']}
    a=np.asarray(first['differential']['coil_factors_per_phase'])
    b=np.asarray(second['differential']['coil_factors_per_phase'])
    difference=abs(a-b);limit=np.maximum(0.001,0.02*abs(b-1))
    if not np.isfinite([*errors.values(),*difference,*limit]).all():raise ValueError('Nonfinite thickness study')
    return {'static_relative_changes':errors,'coil_factor_absolute_changes':difference.tolist(),
            'coil_factor_limits':limit.tolist(),'passed':bool(max(errors.values())<=0.02 and np.all(difference<=limit))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--version',type=int,required=True,help='zero-based saved version')
    parser.add_argument('--thickness-mm',type=float,nargs='+',required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    if not np.isfinite(args.thickness_mm).all() or not all(0<t<=100 for t in args.thickness_mm) or len(set(args.thickness_mm))!=len(args.thickness_mm):
        parser.error('provide distinct positive thicknesses no greater than 100 mm')
    config,stack,geometry,mu,bsat,source_hash=inputs(args.project,args.version)
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):parser.error('work directory must be empty; preserve prior studies')
    report={'scope':__doc__,'status':'running','source_project':str(args.project.resolve()),'source_sha256':source_hash,
            'version_index':args.version,'original_stack':stack,'geometry':geometry,'trials':{},'failures':[],
            'excluded_finite_geometry':{'magnet_count':config['magnet_count'],'magnet_cross_width_mm':config['magnet_cross_width_mm']},
            'warnings':['The housing is nonmagnetic and DC-transparent here. This is not a housing eddy-current study.',
                        'The two sinusoidal coil alignments do not determine the minimum inductance of an imported winding.',
                        'Material constants are ideal two-slope inputs, not measured frequency/temperature-dependent BH data.',
                        'Every trial is numerically checked; geometry/material overrides still require independent FEM verification.']}
    report['source_snapshots']=capture(work,[Path(__file__),Path(__file__).parent/'spectral_plate.py',
        Path(__file__).parent/'spectral_incremental.py',Path(__file__).parent/'vector_harmonic_screen.py',
        Path(__file__).parent/'check_project_spectral.py',Path(femm.__file__)])
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    for thickness_mm in args.thickness_mm:
        name=f'{thickness_mm:g}mm';trial={'thickness_m':thickness_mm*1e-3,'runs':{},'refinements':{}}
        report['trials'][name]=trial;save()
        previous=None
        for tag,cells,modes,samples in [('base',32,9,512),('depth',64,9,512),('modes',64,17,512),('angles',64,17,1024)]:
            result={'static':solve(thickness_mm*1e-3,mu,bsat,cells,modes,samples,geometry),
                    'differential':response(thickness_mm*1e-3,mu,bsat,cells,modes,samples,geometry)}
            trial['runs'][tag]=result
            if previous:
                check=refinement_errors(trial['runs'][previous],result);trial['refinements'][tag]=check
                if not check['passed']:report['failures'].append(f'{name}: {previous}->{tag} refinement failed')
            previous=tag;save()
        final=trial['runs']['angles']
        trial['periodic_reference']={'field_ratio_at_pm_centre_pcb_top':final['static']['field_ratio'],
            'mean_pressure_over_magnet_width_pa':final['static']['pressure_pa'],
            'isolated_two_sheet_dc_factors_per_alignment':final['differential']['coil_factors_per_phase'],
            'quadrature_sampled_peak_b_t':final['differential']['quadrature_sampled_peak_b_t'],
            'quadrature_saturated_fraction':final['differential']['quadrature_saturated_fraction']}
        save();print(name,json.dumps(trial['periodic_reference']),flush=True)
    if hashlib.sha256(args.project.read_bytes()).hexdigest()!=source_hash:raise ValueError('Source project changed during study')
    report['status']='failed' if report['failures'] else 'numerically-converged-periodic-reference'
    save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
