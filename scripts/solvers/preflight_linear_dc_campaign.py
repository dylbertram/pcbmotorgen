#!/usr/bin/env python3
"""Nonnumerical CLI/DAG/path/budget inspection before an overnight launch.

CLI probes use the real script parser, then STOP at parse_args. threaded_main
is intercepted before it imports NGSolve or creates a TaskManager. No solver,
CAD/mesh, source cache or campaign job is launched. Only trusted local solver
scripts are eligible. This inspection is not numerical qualification.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys

from post_project_force import sha
from run_linear_dc_campaign import validate_campaign

HERE=Path(__file__).resolve().parent
OUTPUTS={'work','output','audit_plan'}


def output_paths(parsed):
    # Section/bare-force auditors call their INPUT source --work and write to
    # --output. A generic "every --work is output" rule would create false
    # collisions with their producer. Work-directory solvers have no --output.
    names=OUTPUTS-{'work'} if parsed.get('output') else OUTPUTS
    return [Path(parsed[name]).resolve() for name in names if parsed.get(name)]


def parser_probe(script,arguments):
    """Executed in a child interpreter so parser/global changes cannot leak."""
    import solver_threads
    solver_threads.threaded_main=lambda main:main()
    class Captured(BaseException):
        pass
    original=argparse.ArgumentParser.parse_args
    captured={}
    def parse(parser,args=None,namespace=None):
        value=original(parser,args,namespace)
        captured.update(vars(value))
        raise Captured()
    argparse.ArgumentParser.parse_args=parse
    sys.argv=[str(script),*arguments]
    try:runpy.run_path(str(script),run_name='__main__')
    except Captured:pass
    else:raise ValueError('No parser interception occurred; script is not eligible')
    print('PARSER_CAPTURED_ONLY:'+json.dumps(captured,default=str,allow_nan=False),flush=True)


def probe(python,args,solver_root=HERE):
    script=(Path(solver_root)/args[0]).resolve()
    if not script.is_relative_to(HERE) or script.suffix!='.py' or not script.is_file():raise ValueError('Trusted existing local Python solver entry required')
    source=script.read_text()
    if 'parse_args(' not in source:raise ValueError('Entry has no interceptable parser')
    output=subprocess.run([str(python),str(Path(__file__).resolve()),'--probe',str(script),*args[1:]],
        capture_output=True,text=True,timeout=30)
    lines=[line for line in output.stdout.splitlines() if line.startswith('PARSER_CAPTURED_ONLY:')]
    if output.returncode!=0 or len(lines)!=1:raise ValueError('Actual CLI parser rejected argv: '+output.stderr[-3000:])
    return json.loads(lines[0].split(':',1)[1]),sha(script)


def schedule_budgets(spec,launch_margin_s=30):
    """List schedule on declared resources, plus an order-independent lower bound.

This is not a runtime promise. Sum full explicit timeouts, never best partial
field timings. A failed fit cannot authorize dropping matrix jobs or gates.
"""
    jobs={j['name']:j for j in spec['jobs']};done={j['name']:0. for j in spec['jobs'] if j.get('prior')}
    pending=[j for j in spec['jobs'] if not j.get('prior')];running=[];now=0.;timeline=[]
    while pending or running:
        used=sum(item['memory_gib'] for item in running)
        for job in list(pending):
            if not all(name in done for name in job.get('depends',[])):continue
            if len(running)>=spec['max_parallel'] or used+job['memory_gib']>spec['memory_budget_gib']:continue
            end=now+job['timeout_s']+launch_margin_s
            item=dict(name=job['name'],start_s=now,end_s=end,memory_gib=job['memory_gib'])
            running.append(item);timeline.append(item);pending.remove(job);used+=job['memory_gib']
        if not running:
            if pending:raise ValueError('DAG or declared resource reservation cannot progress')
            break
        now=min(item['end_s'] for item in running)
        for item in list(running):
            if item['end_s']==now:done[item['name']]=now;running.remove(item)
    dependency={}
    for job in spec['jobs']:
        dependency[job['name']]=0. if job.get('prior') else max([dependency[d] for d in job.get('depends',[])]+[0.])+job['timeout_s']+launch_margin_s
    fresh=[j for j in spec['jobs'] if not j.get('prior')]
    lower=max(max(dependency.values(),default=0.),sum(j['timeout_s']+launch_margin_s for j in fresh)/spec['max_parallel'],
        sum((j['timeout_s']+launch_margin_s)*j['memory_gib'] for j in fresh)/spec['memory_budget_gib'])
    return dict(declared_order_budget_makespan_s=now,necessary_budget_lower_bound_s=lower,timeline=timeline,
        note='Declared-order full-timeout schedule, not a measured completion forecast or an optimal schedule certificate. One campaign owns this complete resource budget; separately overlapping campaigns need a global reservation.')


def audit(spec,start_utc):
    validate_campaign(spec)
    start=datetime.fromisoformat(start_utc.replace('Z','+00:00'));end=datetime.fromisoformat(spec['cutoff_utc'].replace('Z','+00:00'))
    if start.tzinfo is None or end.tzinfo is None or end<=start:raise ValueError('Explicit positive timezone-aware window required')
    for job in spec['jobs']:
        if type(job['timeout_s']) not in [int,float] or not math.isfinite(job['timeout_s']) or job['timeout_s']<=0:
            raise ValueError('Finite positive explicit job timeout required')
        if type(job['memory_gib']) not in [int,float] or not math.isfinite(job['memory_gib']) or job['memory_gib']<=0:
            raise ValueError('Finite positive explicit native memory required')
    root=Path(spec['archive_root']).resolve();errors=[];checked=[];outputs={};inputs={}
    for job in spec['jobs']:
        if job.get('prior'):
            receipt=root/(job['log']+'.command.json');launcher=root/(job['log']+'.launcher.json')
            try:
                r=json.loads(receipt.read_text());l=json.loads(launcher.read_text())
                if r['status']!='completed' or type(r.get('exit_code')) is not int or r['exit_code']!=0 or l['status']!='completed-command-not-numerical-qualification':
                    raise ValueError('Prior is not successfully completed; never adopt it as passed')
                inputs.update({str(p):sha(p) for p in [receipt,launcher]})
            except (OSError,ValueError,KeyError) as error:errors.append(job['name']+':prior:'+str(error))
            continue
        try:
            parsed,digest=probe(spec['python'],job['args']);script=(HERE/job['args'][0]).resolve();inputs[str(script)]=digest
            for path in output_paths(parsed):
                if not path.is_relative_to(root):raise ValueError('Output escapes immutable archive root: '+str(path))
                if path.exists():raise ValueError('Fresh output already exists: '+str(path))
                if str(path) in outputs:raise ValueError('Two jobs share output: '+str(path))
                outputs[str(path)]=job['name']
            for suffix in ['', '.command.json','.launcher.json']:
                if (root/(job['log']+suffix)).exists():raise ValueError('Fresh log/receipt already exists')
            checked.append(dict(name=job['name'],parsed=parsed))
        except (ValueError,OSError,subprocess.TimeoutExpired) as error:errors.append(job['name']+':'+str(error))
    # Missing inputs are eligible only when a named transitive dependency creates
    # the exact file or containing work directory. No invented future prior.
    def ancestors(name):
        job=next(j for j in spec['jobs'] if j['name']==name);result=set(job.get('depends',[]))
        for parent in list(result):result.update(ancestors(parent))
        return result
    for job in spec['jobs']:
        if job.get('prior'):continue
        for value in job.get('inputs',[]):
            path=Path(value).resolve()
            if path.is_file():inputs[str(path)]=sha(path);continue
            producers={owner for output,owner in outputs.items() if path==Path(output) or path.is_relative_to(Path(output))}
            if not producers&ancestors(job['name']):errors.append(job['name']+':missing input without declared producer dependency:'+str(path))
    schedule=schedule_budgets(spec);available=(end-start).total_seconds()
    if schedule['declared_order_budget_makespan_s']>available:errors.append('Complete declared-order timeout schedule does not fit the approved window')
    return dict(status='failed-nonnumerical-prelaunch-audit' if errors else 'passed-nonnumerical-prelaunch-audit-only',scope=__doc__,
        start_utc=start.isoformat(),cutoff_utc=end.isoformat(),available_seconds=available,errors=errors,cli_checks=checked,
        schedule=schedule,input_hashes=inputs,no_solver_or_campaign_launched=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--start-utc',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=audit(json.loads(args.campaign.read_text()),args.start_utc)
    result['input_hashes'][str(args.campaign.resolve())]=sha(args.campaign)
    with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(result['status'],result['errors'])
    if result['errors']:raise SystemExit(1)


if __name__=='__main__':
    if sys.argv[1:2]==['--probe']:parser_probe(Path(sys.argv[2]),sys.argv[3:])
    else:main()
