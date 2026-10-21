#!/usr/bin/env python3
"""Isolated full-entry/exit time pair with original2% force/heat/energy gates."""
import argparse
import json
import os
from pathlib import Path

from audit_housing_full_controls import change
from audit_housing_motion_controls import load, control_axis
from post_project_force import sha
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['coarse','fine','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous time-control evidence')
    report={'status':'running','scope':__doc__,
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_housing_full_controls.py'),Path(__file__).with_name('audit_housing_motion_controls.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    try:
        first=load(args.coarse);second=load(args.fine);control_axis(first,second,'time');result=change(first,second)
        report.update(status='passed-full-stroke-housing-time-pair-only' if result['passed'] else 'failed',result=result,
            input_hashes={str(p.resolve()/'summary.json'):sha(p/'summary.json') for p in [args.coarse,args.fine]})
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        if not result['passed']:raise ValueError('Full-stroke time pair failed unchanged2% controls')
    except BaseException as error:
        report.update(status='failed',error=str(error));args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');raise


if __name__=='__main__':main()
