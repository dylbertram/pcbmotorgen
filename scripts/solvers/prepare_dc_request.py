#!/usr/bin/env python3
"""Prepare actual host-request copper/current in immutable stage directories.

Runs baseline source/local/return/independent/RT0 stages, never source-refinement
or magnetic acceptance. Every output stays unqualified and no registry entry or
force is created. One owned host group, serial stages and explicit whole budget.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

from audit_dc_case_matrix import Evidence
from audit_finite_dc_controls import MIXED,PRIMAL,load,resistance_check
from check_dc_worker import HERE,problems,required_packages
from check_free_space import run
from dc_preparation import acceptance_matrix,actual_inputs,PREPARATION_TIMEOUT,STAGES,REMAINING,validate_prepared_summary
from finite_copper_single_drill import build
from post_project_force import sha
from prepare_linear_dc_copper import validate_copper_shape,union_gate,closed_return,partition_checks
from recalculate_dc_request import unchanged_request_bytes
from source_snapshot import capture


def geometry(request_path,work):
    digest=sha(request_path);request=json.loads(unchanged_request_bytes(request_path,digest));actual=actual_inputs(request)
    work.mkdir(parents=True);study=work/'study';study.mkdir();(study/'fixture.json').write_text(json.dumps(actual.pop('snapshot'),allow_nan=False)+'\n')
    snapshot=json.loads((study/'fixture.json').read_text());inputs={str(request_path):digest};snapshots=capture(study,[Path(__file__),HERE/'dc_preparation.py'])
    prepared=dict(status='prepared-actual-linear-study-no-source-or-force-acceptance',case='actual-request-'+digest,input_hashes=inputs,
        fixture_sha256=sha(study/'fixture.json'),source_snapshots=snapshots,**actual)
    (study/'summary.json').write_text(json.dumps(prepared,indent=2,allow_nan=False)+'\n')
    provenance=capture(work,[Path(__file__),HERE/'dc_preparation.py',*[HERE/name for name in ['finite_copper_single_drill.py','finite_copper_geometry.py',
        'finite_copper_circuit.py','finite_copper_grouped.py','prepare_linear_dc_copper.py','audit_copper_union_volume.py']]])
    copper,spec=build(snapshot,actual['translation_m']);validate_copper_shape(copper)
    audit=union_gate(snapshot,actual['translation_m'],float(copper.mass));closed,contacts=closed_return(copper,spec,actual['closure']['return_path_m'])
    partition=partition_checks(copper,closed,actual['model']);copper.WriteBrep(str(work/'copper.brep'));closed.WriteBrep(str(work/'closed-copper-for-partition-audit.brep'))
    spec.update(full_physical_via_stubs=[],physical_via_spans=len(snapshot['routing']['vias']),
        active_copper_layers=sorted({v['layer'] for v in snapshot['routing']['segments']}))
    bound={str(p):sha(p) for p in [request_path,study/'summary.json',study/'fixture.json']}
    report=dict(status='completed-finite-copper-geometry-only-unqualified',scope=__doc__,actual_study_work=str(study),input_hashes=bound,
        translation_m=actual['translation_m'],geometry=spec,brep_sha256=sha(work/'copper.brep'),union_audit=audit,return_contact_audit=contacts,
        partition_checks=partition,closed_partition_brep_sha256=sha(work/'closed-copper-for-partition-audit.brep'),
        closed_partition_volume_m3=float(closed.mass),failures=[],source_snapshots=provenance,command_receipt=os.environ['PCB_MOTOR_COMMAND_RECEIPT'])
    returned=work/'return';returned.mkdir();value=dict(status='prepared-physical-dc-return-geometry-only',closure=actual['closure'],
        translation_m=actual['translation_m'],input_hashes=bound,failures=[],source_snapshots=capture(returned,[Path(__file__)]),
        command_receipt=report['command_receipt'])
    unchanged_request_bytes(request_path,digest)
    for name,digest in bound.items():
        if sha(Path(name))!=digest:raise ValueError('Prepared actual geometry inputs changed')
    for name,source in provenance.items():
        if sha(Path(name))!=source['sha256']:raise ValueError('Actual CAD preparation implementation changed during construction')
    for path,value in [(work/'summary.json',report),(returned/'summary.json',value)]:path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--geometry-stage',action='store_true');args=parser.parse_args()
    request_path=args.request.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve earlier actual preparation stages')
    found=problems(required_packages(HERE/'requirements-dc-worker.txt',True))
    if found:raise ValueError('Source preparation installation rejected: '+'; '.join(found))
    if args.geometry_stage:geometry(request_path,work);return
    digest=sha(request_path);request=json.loads(unchanged_request_bytes(request_path,digest));actual_inputs(request)
    work.mkdir(parents=True);started=time.monotonic();receipt=os.environ.get('PCB_MOTOR_COMMAND_RECEIPT')
    report=dict(status='preparing-request-bound-current-source',input_request_sha256=digest,input_hashes={str(request_path):digest},
        request_id=request['request_id'],force_status='unqualified',source_status='preparing',remaining=REMAINING,
        hard_timeout_s=PREPARATION_TIMEOUT,started_at_utc=datetime.now(timezone.utc).isoformat(),stages={},
        source_snapshots=capture(work,[Path(__file__),HERE/'dc_preparation.py']),command_receipt=receipt)
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    def stage(name,script,args):
        remaining=PREPARATION_TIMEOUT-(time.monotonic()-started)
        if remaining<STAGES[name]+10:raise ValueError('Entire '+name+' budget no longer fits; no late stage launched')
        unchanged_request_bytes(request_path,digest);report['stages'][name]=dict(state='running',hard_timeout_s=STAGES[name]);save()
        os.environ['PCB_MOTOR_SOLVER_TIMEOUT']=str(STAGES[name])
        stage_started=time.monotonic()
        try:
            seconds=run([sys.executable,str(HERE/script),*map(str,args)],work,name+'.log',new_process_group=False)
        except BaseException as error:
            report['stages'][name].update(state='failed',error=str(error),seconds=time.monotonic()-stage_started);save();raise
        report['stages'][name].update(state='completed',seconds=seconds);unchanged_request_bytes(request_path,digest);save()
    try:
        cad=work/'geometry';source=work/'source';matrix=work/'matrix.json'
        matrix.write_text(json.dumps(acceptance_matrix(request_path),indent=2)+'\n')
        stage('geometry','prepare_dc_request.py',['--request',request_path,'--work',cad,'--geometry-stage'])
        stage('source','solve_linear_dc_study.py',['--geometry-work',cad,'--matrix',matrix,'--work',source,
            '--mesh','.0002','--curvature-safety','6','--port-fraction','.5','--max-dofs','24000000','--threads','1'])
        stage('active','audit_finite_dc_winding_sections.py',['--work',source,'--output',work/'active.json','--all-eligible','--threads','1'])
        stage('passive','audit_imported_dc_zero_sections.py',['--work',source,'--output',work/'passive.json','--all-eligible-passive','--declared-no-stubs','--threads','1'])
        stage('return','audit_finite_dc_sections.py',['--work',source,'--output',work/'return.json','--threads','1'])
        current=load(source,MIXED);rho=json.loads((cad/'summary.json').read_text())['geometry']['copper_resistivity_ohm_m']
        stage('independent','finite_copper_primal.py',['--mesh-work',source,'--work',work/'independent','--resistivity',rho,'--max-dofs','4000000','--threads','1'])
        agreement=resistance_check(current,load(work/'independent',PRIMAL),.05)
        if not agreement['passed']:raise ValueError('Independent current agreement exceeds unchanged 5% gate')
        stage('rt0','export_rt0_current_source.py',['--current-work',source,'--work',work/'rt0'])
        evidence=Evidence();artifacts={name:str(work/path) for name,path in [('source','source/summary.json'),('active','active.json'),('passive','passive.json'),
            ('return','return.json'),('independent','independent/summary.json'),('rt0','rt0/summary.json')]}
        for name,path in artifacts.items():evidence.report(Path(path),'--output' if name in ['active','passive','return'] else '--work')
        for path,digest in current['study_bindings'].items():
            if evidence.digest(path)!=digest:raise ValueError('Request-bound source study changed')
        evidence.digest(source/'dc-current-potential.sol');evidence.digest(work/'independent/potential.sol');evidence.digest(work/'rt0/rt0-source.npz');evidence.unchanged()
        report.update(status='prepared-request-bound-current-source-not-qualified',source_status='prepared-baseline-needs-refinement',artifacts=artifacts,
            evidence_hashes={str(p):h for p,h in evidence.hashes.items()},independent_current_agreement=agreement,seconds=time.monotonic()-started)
        validate_prepared_summary(report,digest);unchanged_request_bytes(request_path,digest);save()
    except BaseException as error:
        report.update(status='failed-request-bound-current-preparation',source_status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
