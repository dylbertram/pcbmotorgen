#!/usr/bin/env python3
"""Read-only worker liveness audit. Never upgrades a numerical result.

An archived 'running' receipt is not proof of a live worker. Preserve original
receipts and emit a separate observation, including PID-reuse protection where
the runner recorded Linux process identity. No process is signalled.
"""
import argparse
import json
import os
from datetime import datetime,timezone
from pathlib import Path


def process_identity(pid):
    if type(pid) is not int or pid<=1:return None
    try:
        proc=Path('/proc')/str(pid)
        fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'state':fields[0],'start_ticks':int(fields[19]),
                'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'pid_namespace':os.readlink(proc/'ns/pid')}
    except (OSError,ValueError,IndexError):return None


def receipt_liveness(receipt):
    if receipt.get('status')!='running':return {'state':'not-running','receipt_status':receipt.get('status')}
    if type(receipt.get('pid')) is not int or receipt['pid']<=1:
        return {'state':'unknown','reason':'Legacy running receipt does not identify a safe worker PID'}
    current=process_identity(receipt['pid'])
    if current is None or current['state']=='Z':
        return {'state':'stale-running','reason':'Recorded worker is absent or defunct'}
    expected=receipt.get('process_identity')
    if expected is None:
        return {'state':'unknown','reason':'PID exists but legacy receipt cannot rule out PID reuse','observed_process':current}
    if any(current.get(key)!=expected.get(key) for key in ['pid','start_ticks','boot_id','pid_namespace']):
        return {'state':'stale-running','reason':'Process identity no longer matches the recorded worker','observed_process':current}
    return {'state':'live-worker','observed_process':current,'scope':'Liveness only, not numerical convergence or forward progress'}


def inspect(work):
    summary=json.loads((work/'summary.json').read_text())
    receipts={}
    for path in sorted(set(work.rglob('*.command.json'))|set(work.rglob('*.receipt.json'))):
        receipts[str(path.relative_to(work))]=receipt_liveness(json.loads(path.read_text()))
    live=any(value['state']=='live-worker' for value in receipts.values())
    failed=any(value.get('receipt_status') in ['failed','timeout','interrupted','spawn-failed'] for value in receipts.values())
    stale=any(value['state']=='stale-running' for value in receipts.values())
    status=summary.get('status')
    if status=='running':status='incomplete-with-failed-child' if failed else ('live-worker' if live else ('stale-running' if stale else 'unverified-running'))
    return {'observed_at_utc':datetime.now(timezone.utc).isoformat(),'work':str(work),'recorded_summary_status':summary.get('status'),
            'observed_status':status,'receipts':receipts,'scope':__doc__}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=inspect(args.work.resolve());text=json.dumps(report,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:stream.write(text)
    print(text,end='')


if __name__=='__main__':main()
