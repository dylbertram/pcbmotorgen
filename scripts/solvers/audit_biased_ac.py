#!/usr/bin/env python3
"""Audit independent resolution studies of a periodic DC-biased AC comparison.

No finite-array, nonlinear-transient or arbitrary-amplitude qualification is
implied. Inputs, source snapshots, outputs and successful process receipts are
checked from disk; a comparison-only summary is not by itself evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


LEVELS={'base','depth','modes','angles','wall','gap','mesh','far','source'}
PHYSICS={'spectral_plate.py','spectral_incremental.py','spectral_biased_ac.py','vector_harmonic_screen.py'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_verified(path):
    path=Path(path).resolve();record=json.loads(path.read_text())
    if record.get('status')!='comparison-only' or record.get('failures')!=[]:
        raise ValueError('Incomplete or failed AC comparison')
    physics={}
    for source,entry in record['source_snapshots'].items():
        snapshot=path.parent/entry['snapshot']
        if digest(snapshot)!=entry['sha256']:raise ValueError('Changed source snapshot')
        if Path(source).name in PHYSICS:physics[Path(source).name]=entry['sha256']
    if set(physics)!=PHYSICS:raise ValueError('Missing AC physics source snapshots')
    work=Path(record['femm_work'])
    hashes=record['femm_sha256']
    expected={'biased-ac.bias',*[f'biased-ac.{group}.p{phase}.{sheet}' for group in ['none','stack'] for phase in range(2) for sheet in range(2)]}
    if set(hashes)!=expected:raise ValueError('Missing independent FEMM cases')
    for name,entry in hashes.items():
        for key,suffix in [('input','.case.lua'),('output','.out')]:
            if digest(work/(name+suffix))!=entry[key]:raise ValueError('Changed FEMM artifact')
        receipt=json.loads((work/(name+'.receipt.json')).read_text())
        if not (receipt.get('status')=='completed' and receipt.get('exit_code')==0 and
                receipt.get('input_sha256')==entry['input'] and receipt.get('output_sha256')==entry['output']):
            raise ValueError('Missing successful matching FEMM receipt')
    residuals=np.asarray([record['bias_convergence']['relative_gradient_residual'],record['spectral']['linear_residual']])
    if not np.isfinite(residuals).all() or np.any(residuals<0) or np.any(residuals>1e-9):
        raise ValueError('Unconverged bias/AC response')
    for power,work_done in [(record['femm_loss_w'],record['femm_source_work_w']),
                            (record['spectral']['joule_coefficient_w_m2_t2'],record['spectral']['source_work_coefficient_w_m2_t2'])]:
        power=np.asarray(power);work_done=np.asarray(work_done)
        if power.shape!=(2,) or work_done.shape!=(2,) or not np.isfinite([power,work_done]).all() or np.any(power<=0) or np.any(abs(work_done/power-1)>0.02):
            raise ValueError('Unbalanced or invalid independent source-work/loss')
    return record,physics


def observables(record,independent=False):
    if independent:
        factors=np.asarray(record['femm_factors'],dtype=float);loss=np.asarray(record['femm_loss_w'],dtype=float)
    else:
        factors=np.asarray(record['spectral']['coil_factors_per_phase'],dtype=float)
        loss=np.asarray(record['spectral_loss_w'],dtype=float)
    if factors.shape!=(2,2) or loss.shape!=(2,) or not np.isfinite(factors).all() or not np.isfinite(loss).all() or np.any(loss<=0):
        raise ValueError('Invalid complex factors/loss')
    return factors,loss


def changes(first,second,relative=0.02):
    a,pa=first;b,pb=second
    limits=np.column_stack([np.maximum(0.001,relative*abs(b[:,0]-1)),np.maximum(1e-5,relative*abs(b[:,1]))])
    error=abs(a-b);power=abs(pa/pb-1)
    return {'factor_absolute_change':error.tolist(),'factor_limits':limits.tolist(),'loss_relative_change':power.tolist(),
            'passed':bool(np.all(error<=limits) and np.all(power<=relative))}


def audit(records):
    if set(records)!=LEVELS:raise ValueError('Need separate base/depth/modes/angles/wall/gap and FEMM mesh/far/source levels')
    base=records['base'];identity=['case','frequency_hz','material','knee_density']
    for name,record in records.items():
        if any(record[key]!=base[key] for key in identity):raise ValueError('Different physical AC cases')
        observables(record);observables(record,True)
    # Each spectral step changes exactly one resolution. FEMM refinements use
    # the final spectral resolution and change exactly one FEMM control.
    control={'depth':'layer_cells','modes':'modes_per_phase','angles':'angle_samples','wall':'wall_cells','gap':'gap_cells'}
    previous='base';checks={}
    for name,key in control.items():
        a=records[previous];b=records[name]
        if set(a['resolution'])!=set(b['resolution']) or b['resolution'][key]<=a['resolution'][key] or any(a['resolution'][k]!=b['resolution'][k] for k in a['resolution'] if k!=key):
            raise ValueError('Spectral controls were not refined independently')
        for k in ['femm_sha256','source_strip_count','femm_mesh_scale','femm_far_scale']:
            if a[k]!=b[k]:raise ValueError('FEMM changed during spectral refinement')
        checks[name]=changes(observables(a),observables(b));previous=name
    final=records['gap']
    controls={'mesh':'femm_mesh_scale','far':'femm_far_scale','source':'source_strip_count'}
    for name,key in controls.items():
        record=records[name]
        if record['resolution']!=final['resolution']:raise ValueError('Spectral resolution changed during FEMM refinement')
        for other in controls.values():
            if other!=key and record[other]!=final[other]:raise ValueError('FEMM controls changed together')
        if (record[key]>=final[key] if name=='mesh' else record[key]<=final[key]):raise ValueError('FEMM control was not refined')
        checks['femm_'+name]=changes(observables(final,True),observables(record,True))
        checks['agreement_'+name]=changes(observables(record),observables(record,True),relative=0.05)
    checks['agreement']=changes(observables(final),observables(final,True),relative=0.05)
    return {'status':'passed-periodic-small-signal-only' if all(v['passed'] for v in checks.values()) else 'failed',
            'scope':__doc__,'checks':checks}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',action='append',required=True,help='name=summary.json, all nine levels required')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('preserve the previous audit; use a new output')
    paths={};records={};physics=None
    for item in args.level:
        name,value=item.split('=',1)
        if name in records:parser.error('duplicate refinement level')
        record,source=load_verified(value)
        if physics is not None and source!=physics:raise ValueError('Physics implementation changed across the study')
        physics=source;records[name]=record;paths[name]={'path':str(Path(value).resolve()),'sha256':digest(value)}
    report=audit(records);report.update(inputs=paths,physics_sha256=physics,analysis_sha256=digest(__file__))
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report['status']=='failed':raise SystemExit(1)


if __name__=='__main__':main()
