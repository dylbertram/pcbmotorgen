#!/usr/bin/env python3
"""Fixed-physics macOS NGSolve thread benchmark, with successful solve receipts.

Independent processes, forward/reverse count order, unchanged physical inputs,
mesh hashes and 1e-8 field/loss agreement. BLAS is pinned separately to avoid
nested oversubscription. Performance measurements are not new physics accuracy.
"""
import argparse
import json
import os
from pathlib import Path
import re
import statistics
import sys

import numpy as np

from check_free_space import run
from post_project_force import sha
from solver_threads import positive_threads
from source_snapshot import capture


def interpreter_path(path):
    # Resolving the venv's python symlink selects the base interpreter and loses
    # its site-packages. Preserve the absolute venv entry point instead.
    return str(path.expanduser().absolute())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--solver-python',type=Path,required=True)
    parser.add_argument('--threads',type=positive_threads,nargs='+',default=[1,4,8,16])
    parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args();work=args.work.resolve()
    if sys.platform!='darwin':parser.error('This profiler currently uses macOS /usr/bin/time -l')
    if work.exists() or len(set(args.threads))!=len(args.threads) or args.repeats<2:parser.error('New work directory, unique counts and >=2 repeats required')
    for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
    work.mkdir(parents=True);entry=Path(__file__).with_name('ngsolve_periodic_ac.py').resolve()
    report={'status':'running','scope':__doc__,'counts':args.threads,'repeats':args.repeats,
        'cpu_count':os.cpu_count(),'blas_threads':1,'trials':[],'failures':[],
        'source_snapshots':capture(work,[Path(__file__),entry,Path(__file__).with_name('solver_threads.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();baseline=None
    try:
        for repeat in range(args.repeats):
            order=args.threads if repeat%2==0 else list(reversed(args.threads))
            for count in order:
                name=f'threads-{count}-repeat-{repeat+1}';folder=work/name
                command=['/usr/bin/time','-l',interpreter_path(args.solver_python),'-u',str(entry),
                    '--work',str(folder),'--threads',str(count),'--nx','48','--cells','12',
                    '--air-cells','20','--wall-cells','16']
                elapsed=run(command,work,name+'.log')
                solved=json.loads((folder/'summary.json').read_text());receipt=json.loads((work/(name+'.log.command.json')).read_text())
                if solved['status']!='completed-periodic-tensor-ac-unqualified' or solved['failures'] or receipt['status']!='completed' or receipt['exit_code']!=0:
                    raise ValueError('Thread trial did not finish successfully')
                if solved['execution']['ngsolve_task_threads']!=count or not solved['execution']['task_manager_active']:
                    raise ValueError('Requested task threads were not applied')
                fields=np.array([phase['reflection'] for phase in solved['ac']]);loss=np.array([phase['joule_coefficient_w_m2_t2'] for phase in solved['ac']])
                if baseline is None:baseline=(solved['mesh_sha256'],fields,loss)
                if solved['mesh_sha256']!=baseline[0]:raise ValueError('Mesh bytes changed during a thread-only comparison')
                np.testing.assert_allclose(fields,baseline[1],rtol=1e-8,atol=1e-10)
                np.testing.assert_allclose(loss,baseline[2],rtol=1e-8,atol=1e-10)
                text=(work/(name+'.log')).read_text();memory=re.findall(r'(\d+)\s+maximum resident set size',text)
                cpu=re.findall(r'([\d.]+)\s+real\s+([\d.]+)\s+user\s+([\d.]+)\s+sys',text)
                if len(memory)!=1 or len(cpu)!=1:raise ValueError('Missing macOS resource profile')
                wall,user,system=map(float,cpu[0])
                report['trials'].append({'threads':count,'repeat':repeat+1,'wall_seconds':elapsed,
                    'solver_seconds':solved['seconds'],'cpu_seconds':user+system,'cpu_wall_ratio':(user+system)/wall,
                    'maximum_resident_bytes':int(memory[0]),'newton_iterations':solved['bias']['newton_result'][1],
                    'summary_sha256':sha(folder/'summary.json'),'receipt_sha256':sha(work/(name+'.log.command.json'))})
                save();print(name,elapsed,'seconds, CPU/wall',(user+system)/wall,flush=True)
        report['medians']={str(count):statistics.median(trial['wall_seconds'] for trial in report['trials'] if trial['threads']==count) for count in args.threads}
        fastest=min(report['medians'].values())
        report['recommended_threads']=min(count for count in args.threads if report['medians'][str(count)]<=1.1*fastest)
        report['selection']='Smallest tested count within 10% of the fastest median, to leave interface headroom. Performance policy only, not a numerical acceptance gate.'
        report['status']='passed-fixed-physics-thread-benchmark-only';save()
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
