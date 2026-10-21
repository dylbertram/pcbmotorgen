#!/usr/bin/env python3
"""Check independent time/mesh/domain/quadrature controls of finite housing motion.

The coarse time pair is retained even if it fails; only the finer pair can
qualify the selected time resolution. All fields must be whole completed jobs.
These controls concern a nonmagnetic source-only housing baseline, not ferrite,
winding thrust or full motor qualification.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def load(work):
    record=json.loads((work/'summary.json').read_text())
    if not record.get('command_receipt'):raise ValueError('Missing whole-motion supervisor receipt')
    completed_receipt(record)
    if record['status']!='completed-finite-housing-coupled-motion-unqualified' or record['failures']:
        raise ValueError('Unaccepted or incomplete motion trial')
    if len(record['steps'])!=record['request']['steps']:raise ValueError('Missing time steps')
    if sha(work/'mesh.vol')!=record['mesh_sha256']:raise ValueError('Changed housing mesh')
    for entry in record['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Changed archived motion physics')
    if record['maximum_relative_equation_residual']>1e-9 or record['maximum_net_current_relative_error']>1e-9 or record['maximum_step_energy_balance']>.02 or record['integrated_energy_balance']>.02:
        raise ValueError('Motion equation/current/energy gate failed')
    if record['maximum_housing_self_force_n']>record['self_force_limit_n']:raise ValueError('Unresolved housing self-force')
    for entry in record['saved_midpoints']:
        if sha(work/entry['file'])!=entry['sha256']:raise ValueError('Changed midpoint field')
    dt=record['profile']['dt_s'];speed=record['request']['speed'];start=record['profile']['start_offset_m']
    for i,step in enumerate(record['steps']):
        if step['step']!=i or not np.isclose(step['source_offset_m'],start+speed*(i+.5)*dt,rtol=1e-12,atol=1e-14):
            raise ValueError('Trace does not describe the prescribed translating source')
    for output,field in [('joule_energy_j','joule_power_w'),('source_work_energy_j','source_work_w')]:
        recomputed=sum(step[field]*dt for step in record['steps'])
        if not np.isclose(recomputed,record[output],rtol=1e-10,atol=1e-15):raise ValueError('Energy totals differ from time trace')
    return record


def control_axis(a,b,name):
    if a['model']!=b['model'] or a['housing']!=b['housing'] or a['source_summary_sha256']!=b['source_summary_sha256'] or a['version']!=b['version']:
        raise ValueError('Different physical source or solver version')
    changed={key for key in a['request'] if a['request'][key]!=b['request'][key] and key!='save_every'}
    expected={'time':'steps','mesh':'mesh','domain':'far','quadrature':'bonus_order'}[name]
    if changed!={expected}:raise ValueError('Motion resolution controls changed together')
    if (b['request'][expected]>=a['request'][expected] if name=='mesh' else b['request'][expected]<=a['request'][expected]):
        raise ValueError('Motion control was not refined')
    if name in ['time','quadrature'] and a['mesh_sha256']!=b['mesh_sha256']:
        raise ValueError('Time/quadrature control changed mesh bytes')


def changes(a,b):
    checks={}
    for key in ['joule_energy_j','source_work_energy_j','reaction_energy_end_j']:
        error=abs(a[key]/b[key]-1)
        checks[key]={'relative_change':error,'gate':.02,'passed':np.isfinite(error) and error<=.02}
    x=np.array([row['source_offset_m'] for row in a['steps']]);y=np.array([row['source_offset_m'] for row in b['steps']])
    first=np.array([row['housing_source_interaction_force_n'] for row in a['steps']]);second=np.array([row['housing_source_interaction_force_n'] for row in b['steps']])
    order=np.argsort(y);target=np.column_stack([np.interp(x,y[order],second[order,i]) for i in range(3)])
    if x.min()<y.min() or x.max()>y.max():raise ValueError('Do not extrapolate force traces in a refinement comparison')
    error=float(np.linalg.norm(first-target));limit=max(1e-8,.02*float(np.linalg.norm(target)))
    checks['housing_source_force_curve']={'absolute_l2_change_n':error,'limit_n':limit,'passed':error<=limit}
    return {'checks':checks,'passed':bool(all(entry['passed'] for entry in checks.values()))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    order=['base','time48','time96','mesh','domain','quadrature']
    for name in order:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier motion control audits')
    paths={name:getattr(args,name).resolve() for name in order};records={name:load(path) for name,path in paths.items()}
    checks={};failures=[]
    for first,second,axis in [('base','time48','time'),('time48','time96','time'),('time96','mesh','mesh'),('mesh','domain','domain'),('domain','quadrature','quadrature')]:
        control_axis(records[first],records[second],axis);result=changes(records[first],records[second])
        label=first+'->'+second;checks[label]=result
        if not result['passed'] and first!='base':failures.append(label)
    output={'status':'failed' if failures else 'passed-finite-housing-motion-controls-source-only','scope':__doc__,
        'source_summary_sha256':{name:sha(path/'summary.json') for name,path in paths.items()},'checks':checks,'failures':failures,
        'coarse_time_pair_accepted':checks['base->time48']['passed'],
        'selected_time_pair':'time48->time96','source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    # numpy booleans in diagnostic entries are not JSON scalars.
    for result in output['checks'].values():
        for entry in result['checks'].values():entry['passed']=bool(entry['passed'])
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
