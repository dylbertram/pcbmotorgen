#!/usr/bin/env python3
"""Build and check the on-demand Rust periodic reference against Python.

This establishes implementation parity with the separately FEMM/Elmer-checked
periodic model, not new finite-geometry or operating-speed validation.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from spectral_plate import solve
from spectral_incremental import response
from source_snapshot import capture


REPO=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--release',action='store_true')
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):parser.error('preserve earlier runs; use an empty work directory')
    paths=[Path(__file__),REPO/'scripts/solvers/spectral_plate.py',REPO/'scripts/solvers/spectral_incremental.py',REPO/'scripts/solvers/vector_harmonic_screen.py',
        REPO/'crates/pcbmotorgen-simulation/src/backplane/periodic.rs',REPO/'crates/pcbmotorgen-simulation/src/backplane/mod.rs',
        REPO/'crates/pcbmotorgen-simulation/examples/backplane_dump.rs',REPO/'Cargo.lock']
    report={'scope':__doc__,'status':'running','cases':{},'failures':[],'source_snapshots':capture(work,paths)}
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();command=['cargo','build','-p','pcbmotorgen-simulation','--example','backplane_dump']
    if args.release:command.append('--release')
    with (work/'build.log').open('w') as log:
        subprocess.run(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=REPO/'target'/('release' if args.release else 'debug')/'examples/backplane_dump'
    report['build_command']=command;report['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest();save()
    configurations=[('baseline',{'pole_pitch_mm':6.,'magnet_width_mm':5.,'magnet_cross_width_mm':5.,'magnet_height_mm':3.,
        'magnet_count':5,'remanence_t':1.34,'air_gap_mm':0.5,'pcb_thickness_mm':0.8,'periodic_reference':True},
        [('flex_0.2',0.0002,130.,0.25),('flex_5',0.005,130.,0.25),('mnzn_2',0.002,2500.,0.45)]),
        ('heldout',{'pole_pitch_mm':6.5,'magnet_width_mm':4.5,'magnet_cross_width_mm':5.,'magnet_height_mm':2.5,
        'magnet_count':5,'remanence_t':1.2,'air_gap_mm':0.8,'pcb_thickness_mm':1.6,'periodic_reference':True},
        [('override',0.0007,200.,0.35)])]
    for group,geometry,cases in configurations:
        payload={'geometry':geometry,'cases':[{'name':name,'stack':{'layers':[{'material':'flex_ferrite','thickness_m':t,'mu_r':mu,'bsat_t':bsat}],'housing':None}} for name,t,mu,bsat in cases]}
        input_path=work/(group+'.input.json');input_path.write_text(json.dumps(payload,indent=2)+'\n')
        started=time.monotonic()
        with input_path.open() as stdin,(work/(group+'.stdout.jsonl')).open('w') as stdout,(work/(group+'.stderr.log')).open('w') as stderr:
            subprocess.run([str(binary)],cwd=REPO,stdin=stdin,stdout=stdout,stderr=stderr,check=True)
        rows=[json.loads(line) for line in (work/(group+'.stdout.jsonl')).read_text().splitlines()]
        if len(rows)!=len(cases):raise ValueError('Incomplete Rust periodic batch')
        geom={'pole_pitch':geometry['pole_pitch_mm']*1e-3,'pcb':geometry['pcb_thickness_mm']*1e-3,'gap':geometry['air_gap_mm']*1e-3,
              'width':geometry['magnet_width_mm']*1e-3,'height':geometry['magnet_height_mm']*1e-3,'br':geometry['remanence_t']}
        for row,(name,t,mu,bsat) in zip(rows,cases):
            if row['name']!=name:raise ValueError('Rust case order/identity changed')
            native=row['periodic_static_reference'];comparisons=[]
            if len(native['runs'])!=4:raise ValueError('Missing independent native refinements')
            for run in native['runs']:
                expected=solve(t,mu,bsat,run['depth_cells'],run['odd_modes'],run['angular_samples'],geom)
                differential=response(t,mu,bsat,run['depth_cells'],run['odd_modes'],run['angular_samples'],geom,finite_differences=False)
                residual=run['relative_gradient_residual']
                error={'field_relative_error':abs(run['field_ratio_at_pm_centre_pcb_top']/expected['field_ratio']-1),
                       'pressure_relative_error':abs(run['mean_pressure_over_magnet_width_pa']/expected['pressure_pa']-1),
                       'max_reflected_mode_absolute_error_t':float(np.max(abs(np.asarray(run['reflected_normal_modes_t'])-expected['reflected_normal_modes_t']))),
                       'max_dc_benchmark_factor_absolute_error':float(np.max(abs(np.asarray(run['isolated_sheet_dc_factors_per_alignment'])-differential['coil_factors_per_phase'])))}
                linear_residual=run['differential_relative_residual']
                if not np.isfinite([residual,linear_residual,*error.values()]).all() or not 0<=residual<=1e-9 or not 0<=linear_residual<=1e-9 or max(error.values())>1e-7:
                    report['failures'].append(f'{group}/{name}: native implementation differs from Python')
                comparisons.append(error)
            report['cases'][group+'/'+name]={'native':native,'comparisons':comparisons,'batch_seconds_including_preview':time.monotonic()-started}
            print(group,name,'max parity error',max(max(c.values()) for c in comparisons),flush=True);save()
    for path in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=report['source_snapshots'][str(path.resolve())]['sha256']:
            raise ValueError('Source changed during native parity check')
    report['status']='failed' if report['failures'] else 'passed-periodic-implementation-parity';save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
