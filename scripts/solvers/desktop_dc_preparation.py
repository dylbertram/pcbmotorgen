#!/usr/bin/env python3
"""Bounded source-preparation child in the desktop-owned POSIX group.

No detached children or registry mutation. On timeout/memory failure, persist
the final receipt before stopping this entire owned group, including this
supervisor. Rust observes the failed exit and cannot publish a prepared source.
"""
import argparse
import atexit
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from check_dc_worker import HERE,problems,required_packages
from dc_preparation import PREPARATION_TIMEOUT
from job_status import process_identity
from solver_memory_budget import group_memory

MEMORY_LIMIT=13*1024**3
DISK_LIMIT=8*1024**3
DISK_RESERVE=8*1024**3


def resource_violation(footprint,elapsed,disk_bytes,free_bytes):
    if footprint>MEMORY_LIMIT:return 'memory-limit','Preparation exceeded its 13 GiB native physical-footprint guard'
    if elapsed>=PREPARATION_TIMEOUT:return 'timeout','Preparation exceeded its 14400 s whole-job budget'
    if disk_bytes>DISK_LIMIT or free_bytes<DISK_RESERVE:return 'disk-limit','Preparation exceeded its 8 GiB evidence cap or 8 GiB free-disk reserve'
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['request','archive-root','job']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='darwin' or os.getpgrp()!=os.getpid():raise ValueError('Preparation requires its own desktop-owned macOS POSIX process group')
    found=problems(required_packages(HERE/'requirements-dc-worker.txt',True))
    if found:raise ValueError('Source preparation installation rejected: '+'; '.join(found))
    os.environ.pop('PYTHONPATH',None)
    job=args.job.resolve();path=job/'desktop-worker.log.command.json';started=time.monotonic()
    if shutil.disk_usage(job).free<DISK_LIMIT+DISK_RESERVE:raise ValueError('Preparation requires 16 GiB free disk before launching any numerical stage')
    command=[sys.executable,str(HERE/'prepare_dc_request.py'),'--request',str(args.request.resolve()),'--work',str(job/'result')]
    receipt=dict(status='running',command=command,supervisor_pid=os.getpid(),supervisor_identity=process_identity(os.getpid()),
        timeout_seconds=PREPARATION_TIMEOUT,native_memory_limit_bytes=MEMORY_LIMIT,evidence_disk_limit_bytes=DISK_LIMIT,
        free_disk_reserve_bytes=DISK_RESERVE,cleanup_scope='entire-desktop-owned-posix-group')
    with path.open('x') as stream:stream.write(json.dumps(receipt,indent=2)+'\n')
    def save():path.write_text(json.dumps(receipt,indent=2)+'\n')
    with (job/'desktop-worker.log').open('x') as log:
        environment=dict(os.environ,PCB_MOTOR_COMMAND_RECEIPT=str(path))
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=environment)
        def cleanup():
            if child.poll() is not None:return
            try:
                if receipt['status']=='running':
                    receipt.update(status='interrupted',error='Preparation supervisor exited before its numerical child',seconds=time.monotonic()-started);save()
            finally:
                # This process is the verified group leader. An observation,
                # report-write or unexpected Python failure must not orphan CAD.
                os.killpg(os.getpid(),signal.SIGKILL)
        atexit.register(cleanup)
        receipt.update(pid=child.pid,process_identity=process_identity(child.pid));save();peak=0
        while True:
            usage=group_memory(os.getpid());peak=max(peak,usage['physical_footprint_bytes'])
            sample=dict(usage,peak_physical_footprint_bytes=peak,limit_bytes=MEMORY_LIMIT)
            (job/'desktop-preparation-memory.json').write_text(json.dumps(sample,indent=2)+'\n')
            disk_bytes=sum(p.stat().st_size for p in job.rglob('*') if p.is_file())
            violation=resource_violation(usage['physical_footprint_bytes'],time.monotonic()-started,disk_bytes,shutil.disk_usage(job).free)
            if violation:
                receipt.update(status=violation[0],seconds=time.monotonic()-started,error=violation[1],evidence_disk_bytes=disk_bytes)
                save();print(receipt['error'],file=sys.stderr,flush=True);os.killpg(os.getpid(),signal.SIGKILL)
            try:code=child.wait(timeout=1.)
            except subprocess.TimeoutExpired:continue
            receipt.update(status='completed' if code==0 else 'failed',exit_code=code,seconds=time.monotonic()-started,
                peak_physical_footprint_bytes=peak);save()
            if code:
                # A failed stage might have exited before one of its children.
                # Preserve its receipt, then stop the whole verified group.
                log.flush();os.killpg(os.getpid(),signal.SIGKILL)
            return


if __name__=='__main__':main()
