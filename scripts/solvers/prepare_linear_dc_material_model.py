#!/usr/bin/env python3
"""Bind an unmodified app-defined linear magnetic model to a qualified DC source.

The saved PM/ferrite/housing model from the prepared study is used exactly:
no translation, clearance change or material substitution. Exact BRep
partition checks must show disjoint, separated copper/material bodies; any
contact or overlap is a user decision and is refused here. Does not solve fields
or qualify a B-H law, force or temperature.
"""
import argparse
import itertools
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_copper_magnetic_overlap import rectangular_bounds
from audit_finite_dc_controls import MIXED,load
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from prepare_linear_dc_copper import partition_checks
from source_snapshot import capture


def validate_model(model):
    names=[x['name'] for x in model['stack']+model['magnets']]
    if len(names)!=len(set(names)):raise ValueError('Duplicate magnetic body names')
    tags=[x['tag'] for x in model['stack']+model['magnets']]
    if len(tags)!=len(set(tags)) or 1 in tags:raise ValueError('Magnetic body tags must be unique and distinct from air')
    for region in model['stack']:
        rectangular_bounds(region)
        if not np.isfinite(region['mu_r']) or region['mu_r']<1:raise ValueError('Unsupported static permeability')
        if region['mu_r']>1 and not (region.get('bsat_t') or 0)>0:raise ValueError('Soft magnetic region needs an explicit saturation')
    if not any(x['mu_r']>1 for x in model['stack']) or not model['magnets']:raise ValueError('PMs and a soft magnetic region required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copper-work',type=Path,required=True);parser.add_argument('--current-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    origin,current_work,work=[p.resolve() for p in [args.copper_work,args.current_work,args.work]]
    if work.exists():parser.error('Preserve earlier material bindings')
    copper=json.loads((origin/'summary.json').read_text());completed_receipt(copper)
    if copper['status']!='completed-finite-copper-geometry-only-unqualified' or copper['failures']:raise ValueError('Completed exact copper required')
    current=load(current_work,MIXED)
    if current['input_hashes'].get(str(origin/'copper.brep'))!=copper['brep_sha256']:raise ValueError('Current source does not use this exact copper')
    study_path=Path(copper['actual_study_work'])/'summary.json';study=json.loads(study_path.read_text())
    if current.get('study_bindings',{}).get(str(study_path))!=sha(study_path):raise ValueError('Current source is not bound to this prepared study')
    model=study['model'];validate_model(model)
    inputs={str(origin/'summary.json'):sha(origin/'summary.json'),str(origin/'copper.brep'):copper['brep_sha256'],
        str(current_work/'summary.json'):sha(current_work/'summary.json'),str(current_work/'closed-copper.brep'):current['brep_sha256'],
        str(current_work/'dc-current-potential.sol'):current['solution_sha256'],str(study_path):sha(study_path),**copper['input_hashes']}
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Bound input changed: '+path)
    from netgen.occ import OCCGeometry,Box,Pnt
    started=time.monotonic()
    checks=partition_checks(OCCGeometry(str(origin/'copper.brep')).shape,OCCGeometry(str(current_work/'closed-copper.brep')).shape,model)
    if checks!=copper['partition_checks']:
        for key,value in copper['partition_checks'].items():
            if abs(checks[key]['minimum_brep_distance_m']-value['minimum_brep_distance_m'])>1e-12:raise ValueError('Partition differs from prepared copper audit')
    boxes={x['name']:Box(Pnt(*rectangular_bounds(x)[0]),Pnt(*rectangular_bounds(x)[1])) for x in model['stack']+model['magnets']}
    for a,b in itertools.combinations(boxes,2):
        overlap=float((boxes[a]*boxes[b]).mass)
        if abs(overlap)>1e-18:raise ValueError('Saved material bodies overlap;user decision required')
        checks[a+':'+b]=dict(overlap_m3=overlap,minimum_brep_distance_m=float(boxes[a].Distance(boxes[b])))
    work.mkdir(parents=True)
    report=dict(status='completed-approved-disjoint-material-geometry-only',scope=__doc__,model=model,model_delta_z_m=0.,
        approval=dict(status='not-required-unmodified-app-defined-model',move_policy='none',
            basis='Saved model used unchanged;exact BRep partition shows positive separation and zero overlap. No placement decision was made.'),
        input_hashes=inputs,current_source_work=str(current_work),current_source_reused_without_new_solve=True,geometry_checks=checks,failures=[],
        remaining=['coupled zero-current/linear/nonlinear field controls','mesh/domain/quadrature and independent force checks','qualified app integration'],
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in ['audit_copper_magnetic_overlap.py','prepare_linear_dc_copper.py']]]),
        seconds=time.monotonic()-started)
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Bound input changed during material binding')
    (work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(report['status'],json.dumps(checks),flush=True)


if __name__=='__main__':main()
