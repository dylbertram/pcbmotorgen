#!/usr/bin/env python3
"""Audit the planar spectral prototype against separately qualified FEM subsets.

Passing remains planar and static. It does not qualify a production backend,
finite motor/housing geometry, incremental inductance or biased AC transfer.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_result(result):
    values=[result[key] for key in ['field_ratio','pressure_pa','relative_gradient_residual']]
    if not np.isfinite(values).all() or result['pressure_pa']<=0 or not 0<=result['relative_gradient_residual']<=1e-9:
        raise ValueError('Unresolved or unconverged spectral result')
    if len(result['reflected_normal_modes_t'])!=result['modes'] or not np.isfinite(result['reflected_normal_modes_t']).all():
        raise ValueError('Incomplete reflected source modes')


def compare(baseline,refined,references):
    failures=[];changes={}
    for key in ['analysis_sha256','source_kernel_sha256']:
        if not baseline.get(key) or baseline[key]!=refined.get(key):raise ValueError('Physics/solver source changed during the refinement study')
    expected_geometry={'pole_pitch':0.006,'pcb':0.0008,'gap':0.0005,'width':0.005,'height':0.003,'br':1.34}
    for source in [baseline,refined]:
        if source.get('status')!='comparison-only' or source.get('failures'):raise ValueError('Spectral batch is incomplete/failed')
        for case in source['cases'].values():
            runs=case['runs']
            if set(runs)!={'base','depth','modes'}:raise ValueError('Missing separate spectral refinements')
            a,b,c=(runs[tag] for tag in ['base','depth','modes'])
            if not (b['cells']>a['cells'] and b['modes']==a['modes'] and c['cells']==b['cells'] and c['modes']>b['modes']):
                raise ValueError('Depth/mode refinement controls are not independent')
            for r in runs.values():
                valid_result(r)
                if r['geometry']!=expected_geometry:raise ValueError('Independent FEM controls describe a different periodic source geometry')
                if r['geometry']!=a['geometry'] or r['material']!=a['material'] or r['angle_samples']!=a['angle_samples']:
                    raise ValueError('Physics/angle quadrature changed during depth/mode refinement')
            for first,second in [(a,b),(b,c)]:
                for key in ['field_ratio','pressure_pa']:
                    if abs(first[key]/second[key]-1)>0.02:failures.append('Spectral depth/mode change exceeds 2%')
    if set(baseline['cases'])!=set(refined['cases']):raise ValueError('Held-out material set changed')
    for name,case in refined['cases'].items():
        a=baseline['cases'][name]['runs']['modes'];b=case['runs']['base'];final=case['runs']['modes']
        if not (a['cells']==b['cells'] and a['modes']==b['modes'] and b['angle_samples']>a['angle_samples'] and
                a['material']==b['material'] and a['geometry']==b['geometry']):raise ValueError('Angle study does not isolate angle quadrature')
        changes[name]={}
        for key in ['field_ratio','pressure_pa']:
            change=abs(a[key]/b[key]-1);changes[name][key+'_angle_change']=change
            if change>0.02:failures.append(f'{name}: angle quadrature change exceeds 2%')
        if abs(final['field_ratio_error'])>0.05 or abs(final['pressure_error'])>0.05:failures.append(f'{name}: FEMM comparison exceeds 5%')
    if {ref['case'] for ref in references}!={'flex_0.2','flex_5','mnzn_2'}:raise ValueError('Require qualified thin, thick and high-mu FEM controls')
    for ref in references:
        if ref.get('status')!='passed-subset' or ref.get('failures'):raise ValueError('Independent FEM subset has not passed')
        name=ref['case'];actual=refined['cases'][name]['runs']['modes'];expected=ref['runs']['domain']
        if actual['material']!=ref['material_input']:raise ValueError('Spectral/FEM material mismatch')
        for key in ['field_ratio','pressure_pa']:
            error=actual[key]/expected[key]-1;changes[name][key+'_independent_fem_error']=error
            if abs(error)>0.02:failures.append(f'{name}: independent FEM agreement for {key} exceeds 2%')
    return changes,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--refined',required=True,type=Path)
    parser.add_argument('--reference',required=True,type=Path,nargs='+')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    baseline=json.loads(args.baseline.read_text());refined=json.loads(args.refined.read_text())
    changes,failures=compare(baseline,refined,[json.loads(path.read_text()) for path in args.reference])
    report={'scope':__doc__,'status':'failed' if failures else 'passed-planar-static-reference','changes':changes,'failures':failures,
            'source_sha256':{str(path):sha(path) for path in [args.baseline,args.refined,*args.reference]},'analysis_sha256':sha(Path(__file__))}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if failures:raise SystemExit('\n'.join(failures))
    print('PASS: planar static depth/mode/angle refinement and independent FEM comparisons')


if __name__=='__main__':
    main()
