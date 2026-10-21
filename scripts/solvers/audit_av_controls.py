#!/usr/bin/env python3
"""Audit independent 3D coupled sphere mesh/domain/quadrature controls.

The analytic sphere reference includes magnetic feedback and skin diffusion.
Passing it is not qualification of finite moving magnets, nonlinear backplanes
or an actual motor housing. Failed and interrupted trials remain unaccepted.
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
    report=json.loads((work/'summary.json').read_text())
    if not report.get('command_receipt'):raise ValueError('Missing whole-job supervisor receipt')
    completed_receipt(report)
    if report['status']!='completed-coupled-3d-av-sphere-unqualified' or report['failures']:
        raise ValueError('Incomplete or failed coupled sphere study')
    if sha(work/'mesh.vol')!=report['mesh_sha256'] or sha(work/'response.sol')!=report['solution_sha256']:
        raise ValueError('Archived coupled field or mesh changed')
    for entry in report['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Changed archived coupled physics')
    proof=report['proof']
    if proof['relative_equation_residual']>1e-9 or proof['net_volume_current_relative_error']>1e-9 or proof['relative_source_work_joule_balance']>.02:
        raise ValueError('Coupled equation/current/power gate failed')
    if report['sphere_reference']['fe_relative_error']>.05:raise ValueError('Analytical diffusion reference gate failed')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['base','mesh','domain','quadrature']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous coupled control audits')
    order=['base','mesh','domain','quadrature'];paths={name:getattr(args,name).resolve() for name in order}
    records={name:load(path) for name,path in paths.items()};checks={};failures=[]
    for before,after in zip(order,order[1:]):
        a=records[before];b=records[after]
        changed={key for key in a['request'] if a['request'][key]!=b['request'][key]}
        expected={'mesh':'mesh','domain':'far','quadrature':'bonus_order'}[after]
        if changed!={expected}:raise ValueError('Coupled controls changed together: '+after)
        if (b['request'][expected]>=a['request'][expected] if after=='mesh' else b['request'][expected]<=a['request'][expected]):
            raise ValueError('Coupled control was not refined')
        if a['version']!=b['version'] or a['space_orders']!=b['space_orders']:raise ValueError('Backend or physical FE spaces changed')
        result={}
        for quantity in ['joule_power_w','reaction_magnetic_energy_time_average_j']:
            error=abs(a['proof'][quantity]/b['proof'][quantity]-1)
            result[quantity]={'relative_change':error,'gate':.02,'passed':error<=.02}
            if not np.isfinite(error) or error>.02:failures.append(after+'/'+quantity)
        checks[after]=result
    final=records['quadrature']
    output={'status':'failed' if failures else 'passed-coupled-3d-sphere-controls-only','scope':__doc__,
        'source_report_sha256':{name:sha(path/'summary.json') for name,path in paths.items()},
        'checks':checks,'final_reference_relative_error':final['sphere_reference']['fe_relative_error'],
        'loss_over_weak_limit':final['proof']['joule_power_w']/final['sphere_reference']['weak_limit_loss_w'],
        'failures':failures,'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
