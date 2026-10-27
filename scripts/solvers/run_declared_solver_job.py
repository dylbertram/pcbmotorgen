#!/usr/bin/env python3
"""Execute one immutable bounded job, suitable for a one-shot launchd owner.

The owning service must be explicitly launched. No daemon registration, retry,
force acceptance or geometry mutation is performed by this runner.
"""
import argparse
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import time

from check_free_space import run
from post_project_force import sha
from source_snapshot import capture


def validate_job(spec,now=None):
    if spec.get('schema')!='bounded-solver-job-v1':raise ValueError('Explicit bounded job declaration required')
    now=datetime.now(timezone.utc) if now is None else now
    cutoff=datetime.fromisoformat(spec['cutoff_utc'].replace('Z','+00:00'))
    if cutoff.tzinfo is None:raise ValueError('Explicit timezone-aware job cutoff required')
    budget=spec['timeout_s'];memory=spec['native_footprint_limit_bytes']
    if isinstance(budget,bool) or not isinstance(budget,(int,float)) or not math.isfinite(budget) or budget<=0:
        raise ValueError('Positive finite whole-job budget required')
    if (cutoff-now).total_seconds()<budget+30:raise ValueError('Entire job budget must fit before declared cutoff with launch margin')
    if type(memory) is not int or not 0<memory<=18*1024**3:raise ValueError('Positive native memory budget no greater than18GiB required')
    command=spec['command'];log=spec['log']
    if not isinstance(command,list) or not command or any(not isinstance(value,str) or not value or '\0' in value for value in command):
        raise ValueError('Explicit nonempty argv required; no shell command interpolation')
    if Path(log).name!=log or not log.endswith('.log'):raise ValueError('Unique local log filename required')
    if not Path(spec['archive_root']).is_absolute() or not Path(spec['archive_root']).is_dir():raise ValueError('Existing absolute evidence root required')
    if not spec.get('input_hashes'):raise ValueError('Immutable actual inputs and implementation hashes required')
    for path,digest in spec['input_hashes'].items():
        if not Path(path).is_absolute() or sha(Path(path))!=digest:raise ValueError('Declared input changed')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--declaration',type=Path,required=True);args=parser.parse_args()
    declaration=args.declaration.resolve();digest=sha(declaration);spec=json.loads(declaration.read_text());validate_job(spec)
    root=Path(spec['archive_root']);report_path=root/(spec['log']+'.launcher.json')
    report=dict(status='running',scope=__doc__,declaration=str(declaration),declaration_sha256=digest,
        cutoff_utc=spec['cutoff_utc'],timeout_s=spec['timeout_s'],native_footprint_limit_bytes=spec['native_footprint_limit_bytes'],
        source_snapshots=capture(root,[Path(__file__),Path(__file__).with_name('check_free_space.py'),
            Path(__file__).with_name('solver_memory_budget.py'),Path(__file__).with_name('job_status.py')]))
    with report_path.open('x') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    started=time.monotonic();os.environ['PCB_MOTOR_SOLVER_TIMEOUT']=str(spec['timeout_s'])
    try:
        seconds=run(spec['command'],root,spec['log'],memory_limit_bytes=spec['native_footprint_limit_bytes'])
        if sha(declaration)!=digest:raise ValueError('Job declaration changed during execution')
        for path,expected in spec['input_hashes'].items():
            if sha(Path(path))!=expected:raise ValueError('Job physical input or implementation changed during execution')
        report.update(status='completed-command-not-numerical-qualification',seconds=seconds)
    except BaseException as error:
        report.update(status='failed-or-interrupted',error=str(error),seconds=time.monotonic()-started);raise
    finally:
        report_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
