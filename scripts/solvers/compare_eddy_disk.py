#!/usr/bin/env python3
"""Compare finite 3D A-v disk losses with the independent weak-limit oracle.

This does not accept skin-effect, biased magnetic material or moving housings.
Impressed-field work checks power independently of Joule heating. Raw exterior
Poynting traces are reported separately and are unqualified; a fine trial also
showed an exterior gauge/trace artifact. They do not replace source-work balance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from check_eddy_disk import MU0, mean_power, source_input_work, poynting_input


def validate_refinement(a,b,tag):
    for key in ['conductivity','peak_b','disk_radius','thickness','slot']:
        if a[key]!=b[key]:raise ValueError('Physics changed during refinement')
    if tag=='fine':
        # The conductor size is capped by thickness/3 in the geometry.
        if not (min(b['mesh'],b['thickness']/3)<min(a['mesh'],a['thickness']/3) and
                b['air_radius']==a['air_radius'] and b.get('air_mesh',0.004)==a.get('air_mesh',0.004)):
            raise ValueError('Near-mesh comparison must refine the actual conductor size at fixed air settings')
    elif tag!='domain' or not (b['mesh']==a['mesh'] and b['air_radius']>a['air_radius'] and b.get('air_mesh',0.004)==a.get('air_mesh',0.004)):
        raise ValueError('Domain comparison must expand air without changing local or far-air sizes')


def read(work, oracle):
    path=work/'summary.json'
    source=json.loads(path.read_text())
    if source.get('status')!='comparison-only' or source.get('failures'):
        raise ValueError(f'Incomplete or failed A-v diagnostic: {work}')
    request=source['request']
    shape=next((runs for slot,runs in oracle['cases'].items() if math.isclose(float(slot),request['slot'],abs_tol=1e-12)),None)
    if shape is None:raise ValueError('Oracle cross-section is missing')
    for key,other in [('disk_radius','radius'),('thickness','thickness')]:
        if not math.isclose(request[key],oracle['request'][other],rel_tol=1e-12):raise ValueError('Oracle geometry mismatch')
    if len(source['runs'])<2:raise ValueError('Two frequencies are required for the weak-limit check')
    results={};failures=[]
    for frequency,result in source['runs'].items():
        f=float(frequency)
        if MU0*request['conductivity']*2*math.pi*f*request['disk_radius']**2>0.02:
            raise ValueError('Outside the qualified weak-induction comparison regime')
        job=work/f'f{f:g}'
        for file,digest in result['sha256'].items():
            if hashlib.sha256((job/file).read_bytes()).hexdigest()!=digest:raise ValueError('Archived A-v input/log changed')
        files=list(job.glob('**/fields*.vtu'))
        if len(files)!=1:raise ValueError('Missing or ambiguous field output')
        power,_=mean_power(files[0])
        work_input=source_input_work(files[0],f,request['peak_b'])
        flux,_=poynting_input(files[0],request['air_radius'])
        expected=request['conductivity']*(2*math.pi*f)**2*request['peak_b']**2*request['thickness']*shape[-1]['integral_u_m4']/2
        error=power/expected-1
        balance=work_input/power-1
        if abs(error)>0.05:failures.append(f'{work.name} {f:g} Hz: oracle discrepancy {error:.2%} exceeds 5%')
        if abs(balance)>0.02:failures.append(f'{work.name} {f:g} Hz: source/Joule balance {balance:.2%} exceeds 2%')
        if result['incident_field_relative_error']>0.01:failures.append('Applied field mismatch exceeds 1%')
        results[str(f)]={'mean_loss_w':power,'oracle_loss_w':expected,'oracle_error':error,'source_work_w':work_input,
                         'source_work_balance_error':balance,'poynting_trace_error':flux/power-1,
                         'vtu_sha256':hashlib.sha256(files[0].read_bytes()).hexdigest()}
    first=min(float(f) for f in results)
    reference=results[str(first)]['mean_loss_w']/first**2
    for f,result in results.items():
        if abs(result['mean_loss_w']/float(f)**2/reference-1)>0.02:failures.append('Weak-limit frequency-squared scaling failed')
    return source,results,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle',type=Path,required=True)
    for shape in ['plain','slotted']:
        parser.add_argument('--'+shape+'-work',type=Path,required=True)
        parser.add_argument('--'+shape+'-fine',type=Path)
        parser.add_argument('--'+shape+'-domain',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    oracle=json.loads(args.oracle.read_text())
    if oracle.get('status')!='passed-weak-limit' or oracle.get('failures'):raise ValueError('Oracle has not passed refinement')
    report={'scope':__doc__,'status':'running','cases':{},'failures':[],
            'unqualified_quantities':['exterior electric field and Poynting flux'],
            'oracle_sha256':hashlib.sha256(args.oracle.read_bytes()).hexdigest()}
    refined=True
    for shape in ['plain','slotted']:
        runs={};sources={}
        for tag,suffix in [('coarse','_work'),('fine','_fine'),('domain','_domain')]:
            work=getattr(args,shape+suffix)
            if work is None:
                refined=False;continue
            sources[tag],runs[tag],failures=read(work.resolve(),oracle)
            report['failures'].extend(failures)
        for first,second in [('coarse','fine'),('fine','domain')]:
            if first not in runs or second not in runs:continue
            a,b=sources[first]['request'],sources[second]['request']
            validate_refinement(a,b,second)
            if set(runs[first])!=set(runs[second]):raise ValueError('Frequencies changed during refinement')
            for f in runs[first]:
                change=abs(runs[first][f]['mean_loss_w']/runs[second][f]['mean_loss_w']-1)
                if change>0.02:report['failures'].append(f'{shape} {first}->{second}: loss change exceeds 2%')
        report['cases'][shape]=runs
    report['status']='failed' if report['failures'] else ('passed-weak-limit' if refined else 'comparison-only')
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))
    print(report['status']+': finite A-v loss / source-work / independent current-closure oracle')


if __name__=='__main__':
    main()
