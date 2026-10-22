#!/usr/bin/env python3
"""Run a declared DAG of bounded solver jobs, each under its own declared runner.

Every job gets an exclusive bounded declaration hashed at launch, its own
receipt, timeout and native-memory guard via run_declared_solver_job.py. A job
starts only after all dependencies completed; failed/blocked dependencies block
dependents, never retry them. No job starts unless its whole budget fits before
the declared cutoff. Completion is not numerical qualification.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from post_project_force import sha
from run_declared_solver_job import validate_job

HERE=Path(__file__).resolve().parent
DONE='completed-command-not-numerical-qualification'


def validate_campaign(spec):
    if spec.get('schema')!='linear-dc-campaign-v1':raise ValueError('Declared campaign schema required')
    names=[job['name'] for job in spec['jobs']]
    if len(names)!=len(set(names)):raise ValueError('Duplicate campaign job names')
    logs=[job['log'] for job in spec['jobs']]
    if len(logs)!=len(set(logs)):raise ValueError('Duplicate campaign logs')
    known=set()
    for job in spec['jobs']:
        if any(name not in known for name in job.get('depends',[])):raise ValueError('Dependencies must be declared earlier: '+job['name'])
        if job['memory_gib']>spec['memory_budget_gib']:raise ValueError('Job memory exceeds campaign budget: '+job['name'])
        known.add(job['name'])
    if not 1<=spec['max_parallel']<=8 or not 0<spec['memory_budget_gib']<=18:raise ValueError('Bounded campaign concurrency and memory required')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args()
    campaign_path=args.campaign.resolve();digest=sha(campaign_path);spec=json.loads(campaign_path.read_text());validate_campaign(spec)
    evidence=args.evidence.resolve();root=Path(spec['archive_root']);python=spec['python']
    state_path=evidence/(spec['name']+'-campaign-state.json')
    jobs={job['name']:dict(status='pending') for job in spec['jobs']}
    def adopt(job):
        # Adopt a job owned by an earlier campaign only from its own launcher
        # report and receipt; never launch or relaunch it here.
        launcher=root/(job['log']+'.launcher.json');receipt=root/(job['log']+'.command.json')
        report=json.loads(launcher.read_text()) if launcher.exists() else {}
        command=json.loads(receipt.read_text()) if receipt.exists() else {}
        if report.get('status')==DONE and command.get('status')=='completed' and command.get('exit_code')==0:
            jobs[job['name']]=dict(status='completed',prior=True,launcher_sha256=sha(launcher))
        elif report.get('status') in [None,'running']:jobs[job['name']]=dict(status='waiting-external',prior=True)
        else:jobs[job['name']]=dict(status='failed',prior=True,launcher_status=report.get('status'))
    for job in spec['jobs']:
        if job.get('prior'):adopt(job)
    state=dict(status='running',scope=__doc__,campaign=str(campaign_path),campaign_sha256=digest,pid=os.getpid(),
        started_utc=datetime.now(timezone.utc).isoformat(),jobs=jobs)
    def save():
        state['updated_utc']=datetime.now(timezone.utc).isoformat()
        temporary=state_path.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2)+'\n');temporary.replace(state_path)
    with state_path.open('x') as stream:stream.write(json.dumps(state,indent=2)+'\n')
    running={}
    while True:
        for name,process in list(running.items()):
            code=process.poll()
            if code is None:continue
            del running[name];job=next(j for j in spec['jobs'] if j['name']==name)
            launcher=root/(job['log']+'.launcher.json')
            report=json.loads(launcher.read_text()) if launcher.exists() else {}
            jobs[name].update(returncode=code,launcher_status=report.get('status'),seconds=report.get('seconds'),
                status='completed' if code==0 and report.get('status')==DONE else 'failed',finished_utc=datetime.now(timezone.utc).isoformat())
            print('job',name,jobs[name]['status'],code,flush=True);save()
        for job in spec['jobs']:
            if jobs[job['name']]['status']=='waiting-external':
                adopt(job)
                if jobs[job['name']]['status']!='waiting-external':save()
        for job in spec['jobs']:
            entry=jobs[job['name']]
            if entry['status']!='pending':continue
            depends=[jobs[d]['status'] for d in job.get('depends',[])]
            if any(s in ['failed','blocked','not-launched-cutoff','not-launched-input'] for s in depends):
                entry['status']='blocked';save();continue
            if any(s!='completed' for s in depends):continue
            if len(running)>=spec['max_parallel']:continue
            used=sum(next(j for j in spec['jobs'] if j['name']==n)['memory_gib'] for n in running)
            if used+job['memory_gib']>spec['memory_budget_gib']:continue
            script=HERE/job['args'][0]
            paths=[script,*[Path(p) for p in job.get('inputs',[])]]
            missing=[str(p) for p in paths if not p.exists()]
            if missing:entry.update(status='not-launched-input',missing=missing);save();continue
            declaration=dict(schema='bounded-solver-job-v1',cutoff_utc=spec['cutoff_utc'],timeout_s=job['timeout_s'],
                native_footprint_limit_bytes=int(job['memory_gib']*1024**3),
                command=['/usr/bin/time','-l',python,str(script),*job['args'][1:]],archive_root=str(root),log=job['log'],
                input_hashes={str(p.resolve()):sha(p.resolve()) for p in paths})
            try:validate_job(declaration)
            except ValueError as error:
                entry.update(status='not-launched-cutoff' if 'cutoff' in str(error) else 'not-launched-input',error=str(error));save();continue
            path=evidence/(spec['name']+'-'+job['name']+'-job.json')
            with path.open('x') as stream:stream.write(json.dumps(declaration,indent=2)+'\n')
            running[job['name']]=subprocess.Popen([python,str(HERE/'run_declared_solver_job.py'),'--declaration',str(path)],
                stdout=subprocess.DEVNULL,stderr=(evidence/(spec['name']+'-'+job['name']+'.stderr.log')).open('x'))
            entry.update(status='launched',pid=running[job['name']].pid,declaration=str(path),declaration_sha256=sha(path),
                launched_utc=datetime.now(timezone.utc).isoformat())
            print('launch',job['name'],flush=True);save()
        external=any(j['status']=='waiting-external' for j in jobs.values())
        if not running and not external and all(j['status']!='pending' for j in jobs.values()):break
        if not running and not external and not any(j['status']=='pending' and all(jobs[d]['status']=='completed' for d in next(x for x in spec['jobs'] if x['name']==n).get('depends',[]))
                                   for n,j in jobs.items()):
            for entry in jobs.values():
                if entry['status']=='pending':entry['status']='blocked'
            break
        time.sleep(3)
    counts={}
    for entry in jobs.values():counts[entry['status']]=counts.get(entry['status'],0)+1
    state.update(status='finished-all-completed' if counts=={'completed':len(jobs)} else 'finished-with-failures-or-blocked',counts=counts)
    if sha(campaign_path)!=digest:state['status']='campaign-declaration-changed';save();raise SystemExit(2)
    save();print(json.dumps(counts),flush=True)
    if state['status']!='finished-all-completed':raise SystemExit(1)


if __name__=='__main__':main()
