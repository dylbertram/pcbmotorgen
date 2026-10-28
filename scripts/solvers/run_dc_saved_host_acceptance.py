#!/usr/bin/env python3
"""Run the real saved-design Rust host force/reject/cancel acceptance test.

The selected study supplies only declared placement/return; Rust rebuilds the
actual project copper. Solver paths are explicit host configuration. The clean
worker gets no developer PYTHONPATH. This is not observed native WKWebView E2E.
"""
import argparse
import json
import os
from pathlib import Path
import re

from check_free_space import run
from post_project_force import sha
from source_snapshot import capture


def host_environment(original,project,study,python,solver_root,archive,cargo):
    env=dict(original);env.pop('PYTHONPATH',None);env.pop('PCB_MOTOR_DC_QUALIFY_CIRCULAR',None)
    # Data directories may be canonicalized. Executable symlinks may NOT:
    # Python's virtualenv and rustup's CLI dispatch depend on the invoked path.
    env.update(PCB_MOTOR_PROJECT_PATH=str(Path(project).resolve()),PCB_MOTOR_DC_STUDY_REQUEST_PATH=str(Path(study).resolve()),
        PCB_MOTOR_DC_PYTHON=str(Path(python).absolute()),PCB_MOTOR_DC_SOLVER_ROOT=str(Path(solver_root).resolve()),PCB_MOTOR_DC_ARCHIVE_ROOT=str(Path(archive).resolve()),
        OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',PCB_MOTOR_SOLVER_TIMEOUT='840',
        PATH=str(Path(cargo).absolute().parent)+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin')
    return env


def completed_host_result(text,case_id):
    results=[]
    for line in text.splitlines():
        if not line.startswith('{'):continue
        try:value=json.loads(line)
        except ValueError:continue
        if value.get('state')=='completed' and value.get('result'):results.append(value)
    if len(results)!=1 or results[0]['result'].get('qualified_case',{}).get('case_id')!=case_id:
        raise ValueError('Host result does not identify exactly the selected qualified case')
    return results[0]


def cargo_command(cargo,desktop_root):
    # rustup dispatches by argv[0]. Resolving a cargo symlink to the rustup
    # target changes the CLI rather than merely locating the same executable.
    return ['/usr/bin/env','-C',str(Path(desktop_root).resolve()),str(Path(cargo).absolute()),'test',
        'real_saved_geometry_desktop_job_recalculates_requested_force','--','--ignored','--nocapture']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['project','study-request','python','solver-root','archive-root','cargo','desktop-root','work']:
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--case-id',required=True);args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve earlier actual host acceptance evidence')
    paths=[args.project.resolve(),args.study_request.resolve(),args.solver_root.resolve()/'dc_qualified_cases.py',
        args.desktop_root.resolve()/'src/commands/dc_jobs.rs']
    inputs={str(p):sha(p) for p in paths};work.mkdir(parents=True)
    report=dict(status='running',scope=__doc__,input_hashes=inputs,case_id=args.case_id,
        source_snapshots=capture(work,[Path(__file__)]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        environment=host_environment(dict(os.environ),args.project,args.study_request,args.python,
            args.solver_root,args.archive_root,args.cargo)
        os.environ.clear();os.environ.update(environment)
        # Keep the compile/test in this owned group; Rust owns and cleans its
        # own numerical group, with its existing360s whole-job cap.
        seconds=run(cargo_command(args.cargo,args.desktop_root),work,'host-test.log',new_process_group=False)
        text=(work/'host-test.log').read_text();result=completed_host_result(text,args.case_id)
        evidence={}
        for label,pattern in [('completed',r'Real desktop job evidence: (.+)'),('unsupported',r'Unsupported desktop job evidence: (.+)'),
                              ('cancelled',r'Cancelled real desktop numerical job evidence: (.+)')]:
            matches=re.findall(pattern,text)
            if len(matches)!=1:raise ValueError('Missing actual host '+label+' evidence')
            directory=Path(matches[0].strip()).resolve()
            if not directory.is_relative_to(args.archive_root.resolve()/'dc-desktop-jobs'):raise ValueError('Unexpected host evidence root')
            evidence[label]=str(directory)
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Actual saved-design acceptance input changed')
        report.update(status='passed-actual-saved-host-fresh-force-rejection-and-cancel-only',seconds=seconds,
            actual_host_result=result,evidence_directories=evidence,native_ui_interaction='not performed',developer_pythonpath='unset')
        save();print(report['status'],args.case_id,evidence,flush=True)
    except BaseException as error:
        report.update(status='failed-actual-saved-host-acceptance',error=str(error));save();raise


if __name__=='__main__':main()
