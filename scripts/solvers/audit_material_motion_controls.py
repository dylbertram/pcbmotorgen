#!/usr/bin/env python3
"""Compare completed nonlinear ferrite/housing traces under one refinement.

Independent time, material/housing mesh, domain or quadrature changes only.
Material and current forces are checked separately so static attraction cannot
hide a failed drag calculation. No winding, hardware or large-stroke claim.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def trace_checks(record):
    if record['status']!='completed-nonlinear-ferrite-housing-motion-unqualified' or record['failures']:
        raise ValueError('Failed/incomplete nonlinear material motion cannot be qualified')
    request=record['request'];profile=record['profile'];rows=record['steps'];dt=profile['dt_s'];speed=request['speed']
    if len(rows)!=request['steps'] or not rows:raise ValueError('Incomplete nonlinear motion trace')
    old=record['initial_reduced_energy_j']
    for i,row in enumerate(rows):
        numeric=[row[k] for k in ['time_mid_s','source_offset_m','joule_power_w','current_source_work_w','mechanical_source_work_w',
            'reduced_magnetic_energy_end_j','relative_equation_residual','net_current_relative_error','energy_defect_j','energy_limit_j']]
        if not np.isfinite(numeric).all() or not np.isfinite([row['material_source_force_n'],row['housing_source_force_n']]).all():
            raise ValueError('Nonfinite nonlinear trace')
        if row['step']!=i or not np.isclose(row['source_offset_m'],profile['start_offset_m']+speed*(i+.5)*dt,rtol=1e-12,atol=1e-14):
            raise ValueError('Nonlinear trace does not match translating-source request')
        expected=row['current_source_work_w']+speed*row['material_source_force_n'][0]
        if not np.isclose(row['mechanical_source_work_w'],expected,rtol=1e-12,atol=1e-12):raise ValueError('Conservative material work missing from source ledger')
        if row['relative_equation_residual']>1e-10 or row['net_current_relative_error']>1e-9 or row['energy_defect_j']>row['energy_limit_j']:
            raise ValueError('Nonlinear trace equation, current or step-energy gate failed')
        new=row['reduced_magnetic_energy_end_j'];work=row['mechanical_source_work_w'];loss=row['joule_power_w']
        if loss<0:raise ValueError('Negative Joule heat')
        defect=abs((work-loss)*dt-(new-old));scale=max(abs(work)*dt,loss*dt,abs(new-old),1e-30)
        limit=max(.02*scale,128*np.finfo(float).eps*max(abs(new),abs(old),1e-30))
        if not np.isclose(defect,row['energy_defect_j'],rtol=1e-10,atol=1e-18) or not np.isclose(limit,row['energy_limit_j'],rtol=1e-10,atol=1e-18) or defect>limit:
            raise ValueError('Reported nonlinear step-energy defect or limit is inconsistent')
        old=new
    for output,field in [('joule_energy_j','joule_power_w'),('mechanical_source_energy_j','mechanical_source_work_w')]:
        if not np.isclose(sum(r[field]*dt for r in rows),record[output],rtol=1e-10,atol=1e-15):raise ValueError('Nonlinear energy total differs from trace')
    if not np.isclose(rows[-1]['reduced_magnetic_energy_end_j'],record['final_reduced_energy_j'],rtol=1e-12,atol=1e-15):
        raise ValueError('Final reduced energy differs from last endpoint')
    if record['integrated_energy_defect_j']>record['integrated_energy_limit_j']:raise ValueError('Integrated nonlinear energy gate failed')
    work=record['mechanical_source_energy_j'];heat=record['joule_energy_j'];change=record['final_reduced_energy_j']-record['initial_reduced_energy_j']
    defect=abs(work-heat-change);limit=max(.02*max(abs(work),heat,abs(change),1e-30),128*np.finfo(float).eps*max(abs(old),abs(record['initial_reduced_energy_j']),1e-30))
    if not np.isclose(defect,record['integrated_energy_defect_j'],rtol=1e-10,atol=1e-18) or not np.isclose(limit,record['integrated_energy_limit_j'],rtol=1e-10,atol=1e-18) or defect>limit:
        raise ValueError('Reported integrated nonlinear energy defect or limit is inconsistent')


def load(work):
    record=json.loads((work/'summary.json').read_text())
    if not record.get('command_receipt'):raise ValueError('Missing whole nonlinear-motion receipt')
    completed_receipt(record);trace_checks(record)
    if sha(work/'mesh.vol')!=record['mesh_sha256'] or sha(work/'initial-reaction.sol')!=record['initial_solution_sha256']:
        raise ValueError('Nonlinear material mesh or initial field changed')
    for entry in record['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Archived nonlinear implementation changed')
    return record


def control_axis(first,second,axis):
    for key in ['model','source_summary_sha256','version']:
        if first[key]!=second[key]:raise ValueError('Different nonlinear physical model or solver')
    ignore={'save_every','max_dofs'};a=first['request'];b=second['request']
    changed={k for k in set(a)|set(b) if k not in ignore and a.get(k)!=b.get(k)}
    allowed={'time':{'steps'},'mesh':{'mesh','fer_mesh'},'domain':{'far'},'quadrature':{'bonus_order'},'assembly':set()}[axis]
    if (axis!='assembly' and not changed) or not changed<=allowed:raise ValueError('Nonlinear control changed multiple parameter families')
    for key in changed:
        if not (b[key]<a[key] if axis=='mesh' else b[key]>a[key]):raise ValueError('Nonlinear control did not refine')
    if axis in ['time','quadrature','assembly'] and first['mesh_sha256']!=second['mesh_sha256']:
        raise ValueError('Nonlinear time/quadrature control changed the mesh')
    for key in ['start_offset_m','end_offset_m','duration_s']:
        if first['profile'][key]!=second['profile'][key]:raise ValueError('Different nonlinear motion profiles')


def changes(a,b):
    checks={}
    def check(name,first,second,floor):
        first=np.asarray(first);second=np.asarray(second)
        error=float(np.linalg.norm(first-second));limit=max(floor,.02*float(np.linalg.norm(second)))
        checks[name]={'absolute_change':error,'limit':limit,'passed':bool(np.isfinite(error) and error<=limit)}
    for key in ['joule_energy_j','mechanical_source_energy_j']:
        check(key,a[key],b[key],1e-12)
    # Compare reaction/interaction energy CHANGES, not a large static negative
    # offset that could hide an inaccurate dynamic component.
    check('energy_change_j',a['final_reduced_energy_j']-a['initial_reduced_energy_j'],b['final_reduced_energy_j']-b['initial_reduced_energy_j'],1e-12)
    x=np.array([r['time_mid_s'] for r in a['steps']]);y=np.array([r['time_mid_s'] for r in b['steps']])
    if x.min()<y.min()-1e-15 or x.max()>y.max()+1e-15:raise ValueError('No midpoint extrapolation in nonlinear control')
    for field in ['joule_power_w','housing_source_force_n','material_source_force_n']:
        first=np.array([r[field] for r in a['steps']]);second=np.array([r[field] for r in b['steps']])
        target=np.interp(x,y,second) if second.ndim==1 else np.column_stack([np.interp(x,y,second[:,i]) for i in range(3)])
        floor=(1e-10 if field=='joule_power_w' else 1e-8)*np.sqrt(len(x));check(field,first,target,floor)
    t0=np.array([0.]+[(i+1)*a['profile']['dt_s'] for i in range(len(a['steps']))]);t1=np.array([0.]+[(i+1)*b['profile']['dt_s'] for i in range(len(b['steps']))])
    e0=np.array([a['initial_reduced_energy_j']]+[r['reduced_magnetic_energy_end_j'] for r in a['steps']])-a['initial_reduced_energy_j']
    e1=np.array([b['initial_reduced_energy_j']]+[r['reduced_magnetic_energy_end_j'] for r in b['steps']])-b['initial_reduced_energy_j']
    check('stored_energy_change_history_j',e0,np.interp(t0,t1,e1),1e-12*np.sqrt(len(t0)))
    return {'checks':checks,'passed':all(c['passed'] for c in checks.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coarse',type=Path,required=True);parser.add_argument('--fine',type=Path,required=True)
    parser.add_argument('--axis',choices=['time','mesh','domain','quadrature','assembly'],required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous nonlinear control evidence')
    a=load(args.coarse);b=load(args.fine);control_axis(a,b,args.axis);result=changes(a,b)
    output={'status':'passed-nonlinear-material-motion-'+args.axis+'-control-only' if result['passed'] else 'failed',
        'scope':__doc__,'result':result,'source_summary_sha256':[sha(p/'summary.json') for p in [args.coarse,args.fine]],
        'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if not result['passed']:raise SystemExit('Nonlinear motion refinement failed')


if __name__=='__main__':main()
