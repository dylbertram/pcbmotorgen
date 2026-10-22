#!/usr/bin/env python3
"""Declare and bootstrap one bounded job plus its independent one-shot watcher.

Writes an exclusive declaration, refuses occupied labels/evidence, and never
retries. Completion or liveness is not numerical qualification.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from job_status import process_identity
from one_shot_launchd import bootstrap
from post_project_force import sha

HERE=Path(__file__).resolve().parent
ROOT=Path.home()/'.local/opt/solver-prototypes-macos'
PYTHON=ROOT/'ngsolve-venv/bin/python'
EVIDENCE=ROOT/'linear-dc-day-detached-supervision-v1-20261022'
ENVIRONMENT=dict(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',PYTHONPATH=str(ROOT/'pyamg-5.3.0-arm64'))


def launched_pid(label,attempts=20):
    for _ in range(attempts):
        text=subprocess.run(['launchctl','print','gui/'+str(__import__('os').getuid())+'/'+label],capture_output=True,text=True).stdout
        pids=[line.split('=')[1].strip() for line in text.splitlines() if line.strip().startswith('pid =')]
        if pids:return int(pids[0])
        time.sleep(.25)
    raise RuntimeError('Owned one-shot job did not report a live PID; inspect its logs')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True,help='short label suffix, e.g. case-a-source-v1')
    parser.add_argument('--log',required=True);parser.add_argument('--cutoff',default='2026-10-22T18:29:49.742086Z')
    parser.add_argument('--timeout',type=float,required=True);parser.add_argument('--memory-gib',type=float,required=True)
    parser.add_argument('--input',type=Path,action='append',default=[],help='immutable physical input or implementation')
    parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:parser.error('Explicit solver argv required')
    inputs={str(path.resolve()):sha(path.resolve()) for path in args.input}
    spec=dict(schema='bounded-solver-job-v1',cutoff_utc=args.cutoff,timeout_s=args.timeout,
        native_footprint_limit_bytes=int(args.memory_gib*1024**3),command=['/usr/bin/time','-l',str(PYTHON),*command],
        archive_root=str(ROOT),log=args.log,input_hashes=inputs)
    from run_declared_solver_job import validate_job
    validate_job(spec)
    declaration=EVIDENCE/(args.name+'-job.json')
    with declaration.open('x') as stream:stream.write(json.dumps(spec,indent=2)+'\n')
    label='com.pcbmotorgen.dc.20261022.'+args.name
    worker=bootstrap(label,[str(PYTHON),str(HERE/'run_declared_solver_job.py'),'--declaration',str(declaration)],EVIDENCE,ENVIRONMENT)
    pid=launched_pid(label)
    config=dict(root=str(ROOT),groups=[dict(label=args.name,supervisor_pid=pid,supervisor_identity=process_identity(pid),patterns=[args.log+'.command.json'])])
    config_path=EVIDENCE/(args.name+'-watch-config.json')
    with config_path.open('x') as stream:stream.write(json.dumps(config,indent=2)+'\n')
    watcher=bootstrap(label+'-watch',[str(PYTHON),str(HERE/'watch_solver_jobs.py'),'--config',str(config_path),'--work',str(EVIDENCE/(args.name+'-watch')),
        '--interval','15','--seconds',str(int(args.timeout+120)),'--stale-seconds','300'],EVIDENCE)
    print(json.dumps(dict(worker=worker,watcher=watcher,pid=pid,declaration=str(declaration),declaration_sha256=sha(declaration)),indent=2))


if __name__=='__main__':main()
