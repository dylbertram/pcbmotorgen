#!/usr/bin/env python3
"""One bounded, traced periodic nonlinear ripple trial, not a motor rating.

Each trial must satisfy nonlinear equations, periodic settlement and independent
source-work/Joule balance. Separate time/spatial refinement and an independent
nonlinear implementation are still required before accepting an amplitude
envelope. Incident field fraction is not winding current or permissible PWM.
"""
import argparse
import json
import os
from pathlib import Path
import time

from check_spectral_transient import linearization
from post_project_force import sha
from source_snapshot import capture
from spectral_transient import run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--case',choices=['flex_0.2','flex_1','mnzn_2'],default='mnzn_2')
    parser.add_argument('--fraction',type=float,default=.001);parser.add_argument('--phase',type=int,choices=[0,1],default=0)
    parser.add_argument('--cells',type=int,default=32);parser.add_argument('--modes',type=int,default=9)
    parser.add_argument('--samples',type=int,default=512);parser.add_argument('--wall-cells',type=int,default=32)
    parser.add_argument('--gap-cells',type=int,default=4);parser.add_argument('--steps',type=int,default=128)
    parser.add_argument('--periods',type=int,default=8);parser.add_argument('--harmonic-initial-guess',action='store_true')
    args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve earlier nonlinear trials')
    work.mkdir(parents=True)
    snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
        ['spectral_transient.py','spectral_biased_ac.py','spectral_incremental.py','spectral_plate.py',
         'vector_harmonic_screen.py','check_spectral_transient.py']]])
    thickness,mu,bsat,sigma={'flex_0.2':(.0002,130.,.25,0.),'flex_1':(.001,130.,.25,0.),'mnzn_2':(.002,2500.,.45,.2)}[args.case]
    request={'thickness':thickness,'mu':mu,'bsat':bsat,'frequency':100000.,'fraction':args.fraction,'phase':args.phase,
        'cells':args.cells,'modes':args.modes,'samples':args.samples,'wall_cells':args.wall_cells,'gap_cells':args.gap_cells,
        'steps_per_period':args.steps,'periods':args.periods,'layer_conductivity':sigma,'harmonic_initial_guess':args.harmonic_initial_guess}
    report={'status':'running','scope':__doc__,'case':args.case,'request':request,'source_snapshots':snapshots,'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=time.monotonic()
    try:
        result=run(**request,trace_path=work/'last-two-periods.npz')
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Transient implementation changed during trial')
        report.update(status='completed-periodic-nonlinear-transient-unqualified',result=result,
            linearization=linearization(result),seconds=time.monotonic()-started)
        save();print(report['linearization'],flush=True)
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
