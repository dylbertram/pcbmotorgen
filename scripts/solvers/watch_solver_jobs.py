#!/usr/bin/env python3
"""Read-only watchdog for explicitly selected solver chains.

Never signals jobs or edits their receipts/results. Exits on a new error so
the background completion notification can bring the observation to the agent.
File silence is not itself a solver failure; busy descendants are reported.
Completion observed here never establishes numerical qualification.
"""
import argparse
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time

from job_status import receipt_liveness
from source_snapshot import capture


ERRORS=['Traceback (most recent call last):','FAILED:','Error   :','DIVERGED_',
    'ERROR::','NOT CONVERGED','Segmentation fault','SIGBUS']
FAILURES=['failed','timeout','interrupted','spawn-failed','invalid-process-handle']


def process_table():
    result=subprocess.run(['ps','-axo','pid=,ppid=,%cpu=,rss='],capture_output=True,text=True,timeout=10,check=True)
    table={}
    for line in result.stdout.splitlines():
        pid,parent,cpu,rss=line.split();table[int(pid)]={'parent':int(parent),'cpu_percent':float(cpu),'rss_bytes':int(rss)*1024}
    return table


def descendants(pid,table):
    selected={pid}
    while True:
        children={p for p,value in table.items() if value['parent'] in selected}
        if children<=selected:break
        selected|=children
    return {'cpu_percent':sum(table[p]['cpu_percent'] for p in selected if p in table),
        'rss_bytes':sum(table[p]['rss_bytes'] for p in selected if p in table),'processes':len(selected)}


def summary_path(receipt,root):
    command=receipt.get('command',[])
    for flag in ['--output','--work']:
        if flag in command and command.index(flag)+1<len(command):
            path=Path(command[command.index(flag)+1])
            if not path.is_absolute():path=root/path
            if flag=='--work':path=path/'summary.json'
            return path
    return None


def observe(path,previous,now,table,stale_seconds):
    value=json.loads(path.read_text());live=receipt_liveness(value);status=value.get('status')
    result={'receipt':str(path),'receipt_status':status,'liveness':live['state'],'alerts':[]}
    log=Path(str(path).removesuffix('.command.json'));summary=summary_path(value,path.parent)
    stats=[];raw=None
    for target in [log,summary]:
        if target and target.exists():
            stat=target.stat();stats.append([str(target),stat.st_size,stat.st_mtime_ns])
    signature=json.dumps(stats);last=previous.get('last_activity',now)
    if signature!=previous.get('signature'):last=now
    result.update(signature=signature,last_activity=last,quiet_seconds=max(0.,now-last))
    if log.exists():
        size=log.stat().st_size;offset=previous.get('log_offset',0)
        if offset>size:offset=0
        with log.open('rb') as stream:
            stream.seek(max(0,offset-128,size-1024*1024));text=stream.read().decode('utf8',errors='replace')
        result['log_offset']=size
        # Only search when new bytes arrived, avoiding repeated old warnings.
        if size!=previous.get('log_offset',-1):
            found=[marker for marker in ERRORS if marker in text]
            if found:result['alerts'].append('recent error output: '+', '.join(found))
    if summary and summary.exists():
        try:
            raw=json.loads(summary.read_text());result['summary']=str(summary)
            result['summary_status']=raw.get('status')
            if isinstance(raw.get('steps'),list):result['recorded_steps']=len(raw['steps'])
            if isinstance(raw.get('levels'),dict):result['recorded_levels']=list(raw['levels'])
        except (OSError,ValueError):result['summary_status']='temporarily-unreadable'
    if status in FAILURES:result['alerts'].append('whole-job receipt reports '+status)
    if status=='completed' and (type(value.get('exit_code')) is not int or value['exit_code']!=0):
        result['alerts'].append('completed receipt has no successful integer exit code')
    if status=='completed' and raw and (raw.get('status') in ['running','failed'] or raw.get('failures')):
        result['alerts'].append('completed receipt disagrees with numerical report')
    suspect=status=='running' and live['state'] in ['stale-running','unknown']
    result['suspect_observations']=previous.get('suspect_observations',0)+1 if suspect else 0
    if result['suspect_observations']>=2:result['alerts'].append('worker absent, reused or unverifiable on consecutive checks')
    if status=='running' and live['state']=='live-worker':
        result['resources']=descendants(value['pid'],table)
        if result['quiet_seconds']>=stale_seconds:
            if value['pid'] not in table:result['activity']='quiet-cpu-observation-unavailable'
            elif result['resources']['cpu_percent']>=5:result['activity']='busy-without-new-file-output'
            else:result['alerts'].append('no file progress and little observed CPU; investigate possible stall')
        else:result['activity']='recent-file-activity'
    result['scope']='Health observation only; not convergence, mesh qualification or acceptance'
    return result


def save(path,report):
    temporary=path.with_suffix('.partial');temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--interval',type=float,default=60.)
    parser.add_argument('--seconds',type=float,default=28800.);parser.add_argument('--stale-seconds',type=float,default=1200.)
    args=parser.parse_args()
    if any(not math.isfinite(n) or n<=0 for n in [args.interval,args.seconds,args.stale_seconds]):
        parser.error('Positive finite monitoring durations required')
    config=json.loads(args.config.read_text());root=Path(config['root']).resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous watchdog observations')
    work.mkdir(parents=True);snapshots=capture(work,[Path(__file__),Path(__file__).with_name('job_status.py')])
    started=time.monotonic();previous={};last_summary=None;bad_reads={}
    while True:
        now=time.monotonic();observations={};alerts=[];parents=[]
        try:table=process_table()
        except (OSError,ValueError,subprocess.SubprocessError):table={}
        for group in config['groups']:
            parent=receipt_liveness({'status':'running','pid':group['supervisor_pid'],'process_identity':group['supervisor_identity']})
            parents.append({'label':group['label'],'state':parent['state']})
            paths=sorted({p for pattern in group['patterns'] for p in root.glob(pattern)})
            for path in paths:
                try:
                    observation=observe(path,previous.get(str(path),{}),now,table,args.stale_seconds)
                    bad_reads[str(path)]=0;observations[str(path)]=observation
                    alerts.extend({'group':group['label'],'receipt':str(path),'reason':reason} for reason in observation['alerts'])
                except (OSError,ValueError,KeyError,IndexError) as error:
                    bad_reads[str(path)]=bad_reads.get(str(path),0)+1
                    observations[str(path)]={'status':'temporarily-unreadable','error':str(error)}
                    if bad_reads[str(path)]>=3:alerts.append({'group':group['label'],'receipt':str(path),'reason':'unreadable on three consecutive checks'})
        done=all(p['state']=='stale-running' for p in parents) and not any(v.get('receipt_status')=='running' for v in observations.values())
        expired=now-started>=args.seconds
        status='attention-required' if alerts else ('chains-finished-observed' if done else ('monitoring-window-ended' if expired else 'watching'))
        report={'status':status,'observed_at_utc':datetime.now(timezone.utc).isoformat(),'monitor_pid':os.getpid(),
            'elapsed_seconds':now-started,'scope':__doc__,'groups':parents,'jobs':observations,'alerts':alerts,'source_snapshots':snapshots}
        save(work/'latest.json',report)
        summary=json.dumps({'status':status,'groups':parents,'jobs':{k:(v.get('receipt_status'),v.get('liveness'),v.get('recorded_steps'),v.get('recorded_levels')) for k,v in observations.items()},'alerts':alerts})
        if summary!=last_summary:
            print(report['observed_at_utc'],summary,flush=True)
            with (work/'events.jsonl').open('a') as out:out.write(json.dumps(report)+'\n')
            last_summary=summary
        previous={k:v for k,v in observations.items() if 'signature' in v}
        if alerts:raise SystemExit(2)
        if done or expired:return
        time.sleep(min(args.interval,max(.01,args.seconds-(time.monotonic()-started))))


if __name__=='__main__':main()
