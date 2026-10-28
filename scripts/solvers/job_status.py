#!/usr/bin/env python3
"""Read-only worker liveness audit. Never upgrades a numerical result.

An archived 'running' receipt is not proof of a live worker. Preserve original
receipts and emit a separate observation, including PID-reuse protection where
the runner recorded Linux or macOS process identity. No process is signalled.
"""
import argparse
import json
import os
import sys
import ctypes
import errno
from datetime import datetime,timezone
from pathlib import Path


class DarwinProcessInfo(ctypes.Structure):
    # proc_bsdinfo from macOS <sys/proc_info.h>, PROC_PIDTBSDINFO = 3.
    _fields_ = [(name,ctypes.c_uint32) for name in [
        'flags','status','xstatus','pid','ppid','uid','gid','ruid','rgid',
        'svuid','svgid','reserved']]+[
        ('comm',ctypes.c_char*16),('name',ctypes.c_char*32)]+[
        (name,ctypes.c_uint32) for name in ['nfiles','pgid','pjobc','tdev','tpgid']]+[
        ('nice',ctypes.c_int32),('start_seconds',ctypes.c_uint64),('start_microseconds',ctypes.c_uint64)]


def darwin_process_identity(pid):
    info=DarwinProcessInfo()
    lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
    query=lib.proc_pidinfo
    query.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int]
    query.restype=ctypes.c_int
    if query(pid,3,0,ctypes.byref(info),ctypes.sizeof(info))!=ctypes.sizeof(info):
        if ctypes.get_errno() in [errno.ESRCH,errno.ENOENT]:return None
        return {'pid':pid,'state':'unknown'}
    if info.pid!=pid or not info.start_seconds:return {'pid':pid,'state':'unknown'}
    libc=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
    sysctl=libc.sysctlbyname
    sysctl.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p,ctypes.c_size_t]
    sysctl.restype=ctypes.c_int
    buffer=ctypes.create_string_buffer(128);length=ctypes.c_size_t(len(buffer))
    if sysctl(b'kern.bootsessionuuid',buffer,ctypes.byref(length),None,0)!=0:return {'pid':pid,'state':'unknown'}
    boot=buffer.value.decode('ascii').strip()
    if not boot:return {'pid':pid,'state':'unknown'}
    return {'pid':pid,'state':'Z' if info.status==5 else 'live',
            'start_ticks':info.start_seconds*1000000+info.start_microseconds,
            'boot_id':boot,'pid_namespace':'darwin-host',
            'identity_source':'proc_pidinfo microsecond start time; kern.bootsessionuuid'}


def process_identity(pid):
    if type(pid) is not int or pid<=1:return None
    try:
        if sys.platform=='darwin':return darwin_process_identity(pid)
        proc=Path('/proc')/str(pid)
        fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'state':fields[0],'start_ticks':int(fields[19]),
                'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'pid_namespace':os.readlink(proc/'ns/pid')}
    except (OSError,ValueError,IndexError):return None


def receipt_liveness(receipt):
    if receipt.get('status')!='running':
        result={'state':'not-running','receipt_status':receipt.get('status')}
        if 'exit_code' in receipt:result['exit_code']=receipt['exit_code']
        return result
    if type(receipt.get('pid')) is not int or receipt['pid']<=1:
        return {'state':'unknown','reason':'Legacy running receipt does not identify a safe worker PID'}
    current=process_identity(receipt['pid'])
    if current is not None and current.get('state')=='unknown':
        return {'state':'unknown','reason':'Worker identity could not be read reliably'}
    if current is None or current['state']=='Z':
        if sys.platform not in ['linux','darwin']:
            return {'state':'unknown','reason':'Process identity is unsupported on this host'}
        return {'state':'stale-running','reason':'Recorded worker is absent or defunct'}
    expected=receipt.get('process_identity')
    if (not isinstance(expected,dict) or type(expected.get('start_ticks')) is not int or expected['start_ticks']<=0
            or any(not isinstance(expected.get(key),str) or not expected[key] for key in ['boot_id','pid_namespace'])):
        return {'state':'unknown','reason':'PID exists but legacy receipt cannot rule out PID reuse','observed_process':current}
    if any(current.get(key)!=expected.get(key) for key in ['pid','start_ticks','boot_id','pid_namespace']):
        return {'state':'stale-running','reason':'Process identity no longer matches the recorded worker','observed_process':current}
    return {'state':'live-worker','observed_process':current,'scope':'Liveness only, not numerical convergence or forward progress'}


def inspect(work,summary_file=None,receipt_file=None):
    work=Path(work).resolve()
    summary_path=work/'summary.json' if summary_file is None else Path(summary_file)
    if not summary_path.is_absolute():summary_path=work/summary_path
    summary=json.loads(summary_path.read_text())
    receipts={}
    paths=set(work.rglob('*.command.json'))|set(work.rglob('*.receipt.json'))
    linked=str(receipt_file) if receipt_file is not None else summary.get('command_receipt')
    if linked is not None:
        if not isinstance(linked,str) or not linked.endswith(('.command.json','.receipt.json')):
            raise ValueError('Invalid explicit supervisor receipt path')
        path=Path(linked)
        # An explicit whole-job supervisor is authoritative for this report.
        # Do not mix unrelated studies when standalone reports share a prefix.
        paths={path if path.is_absolute() else work/path}
    for path in sorted(paths):
        try:key=str(path.relative_to(work))
        except ValueError:key='external:'+str(path)
        try:receipts[key]=receipt_liveness(json.loads(path.read_text()))
        except (OSError,ValueError):receipts[key]={'state':'unknown','reason':'Supervisor receipt is missing or unreadable'}
    live=any(value['state']=='live-worker' for value in receipts.values())
    failed=any(value.get('receipt_status') in ['failed','timeout','interrupted','spawn-failed'] for value in receipts.values())
    stale=any(value['state']=='stale-running' for value in receipts.values())
    status=summary.get('status')
    if failed and status!='failed':status='incomplete-with-failed-child'
    elif status=='running':status='live-worker' if live else ('stale-running' if stale else 'unverified-running')
    elif linked and status!='failed' and any(value.get('receipt_status')!='completed' or type(value.get('exit_code')) is not int or value['exit_code']!=0 for value in receipts.values()):
        status='live-worker' if live else 'unverified-result'
    return {'observed_at_utc':datetime.now(timezone.utc).isoformat(),'work':str(work),'recorded_summary_status':summary.get('status'),
            'observed_status':status,'receipts':receipts,'summary_path':str(summary_path),'scope':__doc__}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--summary',type=Path,help='standalone report to inspect instead of work/summary.json')
    parser.add_argument('--receipt',type=Path,help='explicit whole-job receipt for historical reports without a link')
    args=parser.parse_args();report=inspect(args.work.resolve(),args.summary,args.receipt);text=json.dumps(report,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:stream.write(text)
    print(text,end='')


if __name__=='__main__':main()
