#!/usr/bin/env python3
"""Separate numerical-resolution controls for periodic small-signal AC only."""
import argparse
import json
import os
from pathlib import Path

from scipy.sparse import save_npz
import numpy as np

from audit_biased_ac import changes
from post_project_force import sha
from source_snapshot import capture
from spectral_biased_ac import bias_state,complex_response


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--case',choices=['flex_0.2','mnzn_2'],default='mnzn_2')
    args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous spectral studies')
    work.mkdir(parents=True)
    snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
        ['spectral_biased_ac.py','spectral_incremental.py','spectral_plate.py','vector_harmonic_screen.py','audit_biased_ac.py']]])
    t,mu,bsat,sigma={'flex_0.2':(.0002,130.,.25,0.),'mnzn_2':(.002,2500.,.45,.2)}[args.case]
    report={'status':'running','scope':__doc__,'case':args.case,'frequency_hz':100000.,'source_snapshots':snapshots,'levels':{},'checks':{},'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();cache={};previous=None
    try:
        for label,cells,modes,samples,wall,gap in [('base',32,9,512,32,4),('depth',64,9,512,32,4),
            ('modes',64,17,512,32,4),('angles',64,17,1024,32,4),('wall',64,17,1024,64,4),('gap',64,17,1024,64,8)]:
            key=(cells,modes,samples)
            if key not in cache:
                full,hessian,proof=bias_state(t,mu,bsat,cells,modes,samples)
                name=f'hessian-{cells}-{modes}-{samples}.npz';save_npz(work/name,hessian)
                cache[key]=(full,hessian,proof,name)
            full,hessian,proof,name=cache[key]
            response=complex_response(full,hessian,100000.,wall_cells=wall,gap_cells=gap,layer_conductivity=sigma)
            result={'resolution':{'cells':cells,'modes':modes,'samples':samples,'wall':wall,'gap':gap},
                'bias_convergence':proof,'spectral':response,'hessian':name,'hessian_sha256':sha(work/name)}
            report['levels'][label]=result
            if previous is not None:
                quantities=lambda entry:(np.asarray(entry['spectral']['coil_factors_per_phase']),np.asarray(entry['spectral']['joule_coefficient_w_m2_t2']))
                check=changes(quantities(previous),quantities(result))
                report['checks'][label]=check
                if not check['passed']:report['failures'].append(label+' refinement exceeds unchanged gates')
            previous=result;save();print(label,response['reflection_per_phase'],flush=True)
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Spectral study changed during solve')
        report['status']='failed' if report['failures'] else 'passed-periodic-spectral-refinement-only';save()
        if report['failures']:raise ValueError('\n'.join(report['failures']))
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
