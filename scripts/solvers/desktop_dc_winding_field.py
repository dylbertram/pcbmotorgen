#!/usr/bin/env python3
"""Bounded direct field sampling in the desktop's one owned process group."""
import argparse
import atexit
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from check_dc_worker import pins,problems
from job_status import process_identity
from solver_memory_budget import group_memory

TIMEOUT=170
MEMORY_LIMIT=4*1024**3


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['request','archive-root','job']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='darwin' or os.getpgrp()!=os.getpid():raise ValueError('Desktop-owned macOS group required')
    found=problems(pins(Path(__file__).with_name('requirements-dc-worker.txt')))
    if found:raise ValueError('Pinned worker rejected: '+'; '.join(found))
    os.environ.pop('PYTHONPATH',None)
    job=args.job.resolve();path=job/'desktop-worker.log.command.json';start=time.monotonic()
    command=[sys.executable,str(Path(__file__).with_name('sample_dc_winding_field.py')),
        '--request',str(args.request.resolve()),'--archive-root',str(args.archive_root.resolve()),'--work',str(job/'result')]
    receipt=dict(status='running',command=command,timeout_seconds=TIMEOUT,native_memory_limit_bytes=MEMORY_LIMIT,
        supervisor_pid=os.getpid(),supervisor_identity=process_identity(os.getpid()),cleanup_scope='entire-desktop-owned-posix-group')
    with path.open('x') as stream:stream.write(json.dumps(receipt,indent=2)+'\n')
    def save():path.write_text(json.dumps(receipt,indent=2)+'\n')
    with (job/'desktop-worker.log').open('x') as log:
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        def cleanup():
            if child.poll() is None:
                receipt.update(status='interrupted',seconds=time.monotonic()-start);save();os.killpg(os.getpid(),signal.SIGKILL)
        atexit.register(cleanup)
        receipt.update(pid=child.pid,process_identity=process_identity(child.pid));save();peak=0
        while True:
            usage=group_memory(os.getpid());peak=max(peak,usage['physical_footprint_bytes'])
            if peak>MEMORY_LIMIT or time.monotonic()-start>=TIMEOUT:
                receipt.update(status='memory-limit' if peak>MEMORY_LIMIT else 'timeout',peak_physical_footprint_bytes=peak,seconds=time.monotonic()-start)
                save();os.killpg(os.getpid(),signal.SIGKILL)
            try:code=child.wait(timeout=.25)
            except subprocess.TimeoutExpired:continue
            receipt.update(status='completed' if code==0 else 'failed',exit_code=code,peak_physical_footprint_bytes=peak,seconds=time.monotonic()-start);save()
            if code:log.flush();os.killpg(os.getpid(),signal.SIGKILL)
            return


if __name__=='__main__':main()
