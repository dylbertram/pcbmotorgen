#!/usr/bin/env python3
"""Audit independent quadrature refinement of completed low-Rm closure jobs."""
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
    if not report.get('command_receipt'):raise ValueError('Missing whole-job closure receipt')
    completed_receipt(report)
    receipt=json.loads(Path(report['command_receipt']).read_text());command=receipt['command']
    if '--work' not in command or Path(command[command.index('--work')+1]).resolve()!=work.resolve():
        raise ValueError('Closure receipt belongs to a different job')
    for flag,key in [('--sigma','sigma_s_m'),('--speed','speed_m_s')]:
        if flag not in command or float(command[command.index(flag)+1])!=report[key]:
            raise ValueError('Closure conductivity or velocity differs from its executed command')
    if report['status']!='passed-finite-current-closure-low-rm-source-only' or report['failures']:
        raise ValueError('Incomplete or failed finite current closure')
    if report['magnetic_reynolds_number']>.01:raise ValueError('Outside prescribed-field low-Rm regime')
    for entry in report['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Changed archived closure physics')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first',type=Path,required=True);parser.add_argument('--second',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier quadrature audits')
    snapshots=capture(args.output.parent,[Path(__file__)])
    a=load(args.first);b=load(args.second)
    if b['bonus_order']<=a['bonus_order']:raise ValueError('Quadrature was not refined')
    for key in ['version','source_summary_sha256','sigma_s_m','speed_m_s','housing','slot','magnetic_reynolds_number']:
        if a[key]!=b[key]:raise ValueError('Physical input changed during quadrature refinement')
    if a['levels'].keys()!=b['levels'].keys():raise ValueError('Mesh levels changed during quadrature refinement')
    checks={};failures=[]
    for level in a['levels']:
        for shape in ['closed','slotted']:
            filename=f'{shape}-{float(level):.6f}.vol'
            if sha(args.first/filename)!=sha(args.second/filename):raise ValueError('Mesh changed during quadrature refinement')
            x=a['levels'][level][shape]['forward'];y=b['levels'][level][shape]['forward']
            loss=abs(x['joule_power_w']/y['joule_power_w']-1)
            force=float(np.linalg.norm(np.array(x['housing_force_n'])-y['housing_force_n'])/np.linalg.norm(y['housing_force_n']))
            checks[level+'/'+shape]={'loss_relative_change':loss,'force_relative_change':force,'passed':max(loss,force)<=.02}
            if max(loss,force)>.02:failures.append(level+'/'+shape)
    output={'status':'failed' if failures else 'passed-low-rm-closure-quadrature-only','scope':__doc__,
        'source_report_sha256':[sha(p/'summary.json') for p in [args.first,args.second]],
        'gate':.02,'checks':checks,'failures':failures,'source_snapshots':snapshots}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
