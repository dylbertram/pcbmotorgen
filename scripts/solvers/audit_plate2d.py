#!/usr/bin/env python3
"""Audit one complete material subset without accepting an incomplete batch.

Reprocess the original raw potentials and convergence receipts. Never overwrite
the batch summary or turn an unconverged material into a result.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from check_plate2d import measure, reference


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_convergence(log, backend, nonlinear):
    if backend=='elmer':
        changes=re.findall(r'^ComputeChange: NS \(ITER=(\d+)\) \(NRM,RELC\): \(\s*\S+\s+(\S+)\s*\) :: vectorpotential\s*$',log,re.M)
        if not changes or 'System has converged to tolerances' not in log:
            raise ValueError('Missing planar magnetic-potential convergence')
        value=float(changes[-1][1])
        if not np.isfinite(value) or not 0<=value<=1e-9:
            raise ValueError('Planar potential has not reached the original 1e-9 tolerance')
    elif 'CONVERGED_' not in log:
        raise ValueError('Missing GetDP linear convergence')


def assess(runs):
    failures=[]
    for tag,r in runs.items():
        expected=r['reference']['pressure_pa']
        if max(abs(p) for p in r['bare']['stress_path_pressures_pa'])>0.02*abs(expected):
            failures.append(f'{tag}: no-plate force floor exceeds 2%')
        if abs(r['field_ratio_error'])>0.05 or abs(r['pressure_error'])>0.05:
            failures.append(f'{tag}: FEMM agreement exceeds 5%')
        sensitivity=max(abs(p-r['plate']['pressure_pa']) for p in r['plate']['stress_path_pressures_pa'])/abs(r['pressure_pa'])
        if tag!='base' and sensitivity>0.02:failures.append(f'{tag}: stress-path change exceeds 2%')
    for first,second in [('base','fine'),('fine','domain')]:
        for key in ['field_ratio','pressure_pa']:
            if abs(runs[first][key]/runs[second][key]-1)>0.02:
                failures.append(f'{first}->{second}: {key} change exceeds 2%')
    return failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--femm-work',required=True,type=Path)
    parser.add_argument('--case',required=True,choices=['flex_0.2','flex_5','mnzn_2'])
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();work=args.work.resolve()
    if args.output.resolve()==work/'summary.json':parser.error('do not overwrite the original batch summary')
    source=json.loads((work/'summary.json').read_text());saved=source['cases'][args.case]
    if set(saved)!={'base','fine','domain'}:raise ValueError('This material subset is incomplete')
    backend=source['backend'];runs={};hashes={};requests={}
    base_path=args.femm_work/'v2.none.mag.out';ref_path=args.femm_work/f'v2.{args.case}.knee.out'
    expected_base=reference(base_path);expected=reference(ref_path)
    for tag in ['base','fine','domain']:
        results=[]
        for biased,name in [(False,'bare'),(True,'plate')]:
            job=work/f'{args.case}.{tag}.{name}'
            archived=saved[tag][name]
            for path,digest in archived['sha256'].items():
                if sha(job/path)!=digest:raise ValueError(f'Archived input changed: {job/path}')
            receipt=json.loads((job/'solve.log.command.json').read_text())
            if receipt.get('status')!='completed' or receipt.get('exit_code')!=0:raise ValueError('Solve is not complete')
            log=(job/'solve.log').read_text();require_convergence(log,backend,biased)
            request=json.loads((job/'request.json').read_text())
            if request['biased_plate']!=biased or request['backend']!=backend:raise ValueError('Mismatched material/excitation request')
            if backend=='getdp':
                residual=np.loadtxt(job/'nonlinear.txt').reshape(-1,2)[-1]
                if not np.isfinite(residual).all() or (biased and not 0<=residual[0]<=1e-9):raise ValueError('Scalar nonlinearity is unconverged')
                field=job/'potential.pos'
            else:
                fields=list(job.glob('**/fields*.vtu'))
                if len(fields)!=1:raise ValueError('Missing or ambiguous potential output')
                field=fields[0]
            measured=measure(field,request['thickness_m'])
            for key in ['pcb_centre_by_t','pressure_pa','stress_path_pressures_pa']:
                np.testing.assert_allclose(measured[key],archived[key],atol=1e-10,rtol=1e-10)
            results.append(measured)
            hashes[f'{tag}.{name}']={'raw_potential':sha(field),'log':sha(job/'solve.log'),'receipt':sha(job/'solve.log.command.json')}
            requests[f'{tag}.{name}']=request
        bare,plate=results
        ratio=plate['pcb_centre_by_t']/bare['pcb_centre_by_t'];pressure=plate['pressure_pa']-bare['pressure_pa']
        ref_ratio=expected['mag_centre_pcb_top_By']/expected_base['mag_centre_pcb_top_By'];ref_pressure=expected['Fy_stack']/0.01
        runs[tag]={'bare':bare,'plate':plate,'field_ratio':ratio,'pressure_pa':pressure,
                   'field_ratio_error':ratio/ref_ratio-1,'pressure_error':pressure/ref_pressure-1,
                   'reference':{'field_ratio':ref_ratio,'pressure_pa':ref_pressure}}
    first=requests['base.bare']
    for r in requests.values():
        for key in ['mu_initial','saturation_polarization_t','thickness_m']:
            if r[key]!=first[key]:raise ValueError('Physics changed between refinement jobs')
    for tag in ['base','fine','domain']:
        a,b=requests[f'{tag}.bare'],requests[f'{tag}.plate']
        for key in ['mesh_m','air_extent_m']:
            if a[key]!=b[key]:raise ValueError('Bare and plate numerical controls differ')
    coarse,fine,domain=(requests[f'{tag}.plate'] for tag in ['base','fine','domain'])
    if not (fine['mesh_m']<coarse['mesh_m'] and fine['air_extent_m']==coarse['air_extent_m'] and
            domain['mesh_m']==fine['mesh_m'] and domain['air_extent_m']>fine['air_extent_m']):raise ValueError('Not independent mesh/domain refinements')
    failures=assess(runs)
    report={'scope':__doc__,'case':args.case,'backend':backend,'status':'failed' if failures else 'passed-subset',
            'material_input':{key:requests['domain.plate'][key] for key in ['mu_initial','saturation_polarization_t','thickness_m']},
            'original_batch_status':source['status'],'source_sha256':sha(work/'summary.json'),'runs':runs,'failures':failures,
            'sha256':hashes,'femm_sha256':{p.name:sha(p) for p in [base_path,ref_path]},'analysis_sha256':sha(Path(__file__))}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if failures:raise SystemExit('\n'.join(failures))
    print(f'PASS: {args.case} subset only; original batch status {source["status"]} is unchanged')


if __name__=='__main__':
    main()
