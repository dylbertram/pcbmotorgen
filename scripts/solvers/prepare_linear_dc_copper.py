#!/usr/bin/env python3
"""Exact finite copper and explicit return from an actual prepared linear case.

No fitted source geometry, material moves, magnetic solve or force acceptance.
Checks BRep material disjointness and unintended return contacts before meshing.
"""
import argparse
import itertools
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from dc_request_contract import geometry_descriptor
from finite_copper_circuit import return_prism
from audit_copper_union_volume import STANDARD_ERROR_GATE,VOLUME_GATE,primitives,union_estimate
from finite_copper_geometry import build,fuse_all
from finite_copper_grouped import grouped_build
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def load_study(work,receipt_path):
    work=Path(work).resolve();receipt_path=Path(receipt_path).resolve()
    study=json.loads((work/'summary.json').read_text());completed_receipt({'command_receipt':str(receipt_path)})
    receipt=json.loads(receipt_path.read_text());command=receipt['command']
    if '--work' not in command or Path(command[command.index('--work')+1]).resolve()!=work.parent:
        raise ValueError('Study receipt does not describe this actual prepared case')
    if not any(Path(value).name=='prepare_linear_dc_studies.py' for value in command):raise ValueError('Actual case-preparation receipt required')
    if study['status']!='prepared-actual-linear-study-no-source-or-force-acceptance':raise ValueError('Unaccepted actual study inputs')
    if sha(work/'fixture.json')!=study['fixture_sha256']:raise ValueError('Actual host copper snapshot changed')
    for name,digest in study['input_hashes'].items():
        if sha(Path(name))!=digest:raise ValueError('Prepared study physical inputs changed')
    for entry in study['source_snapshots'].values():
        path=(work/entry['snapshot']).resolve()
        if not path.is_relative_to(work) or sha(path)!=entry['sha256']:raise ValueError('Archived study implementation changed')
    snapshot=json.loads((work/'fixture.json').read_text());geometry_descriptor(snapshot)
    return study,snapshot


def validate_copper_shape(copper):
    volume=float(copper.mass)
    if len(copper.solids)!=1 or not np.isfinite(volume) or volume<=0:
        raise ValueError('Actual copper union must be one nonempty solid;no geometry repair or return-only substitute permitted')


def union_gate(snapshot,shift,volume):
    pieces,drills=primitives(snapshot,shift);estimate,error=union_estimate(pieces,drills,4000)
    difference=abs(volume/estimate-1)
    result=dict(primitives=len(pieces),drill_bores=len(drills),analytic_union_volume_m3=estimate,analytic_standard_error_m3=error,
        cad_volume_m3=volume,relative_difference=difference,volume_gate=VOLUME_GATE,standard_error_gate=STANDARD_ERROR_GATE)
    if error/estimate>STANDARD_ERROR_GATE or not difference<=VOLUME_GATE:
        raise ValueError('Exact copper CAD differs from the analytic union of its declared primitives;no repair applied')
    return result


def closed_return(copper,spec,path):
    from netgen.occ import Box,Pnt
    validate_copper_shape(copper)
    points=np.asarray(path,dtype=float);layer=spec['layers'][0]
    if points.shape!=(4,3):raise ValueError('Explicit three-segment finite return required')
    returned=fuse_all([return_prism(a,b,layer['trace_width_m'],layer['thickness_m']) for a,b in zip(points[:-1],points[1:])])
    unintended=returned*copper
    radius=max(spec['via_pad_radius_m'],layer['trace_width_m']/2)
    for endpoint in [points[0],points[-1]]:unintended=unintended-Box(Pnt(*(endpoint-radius)),Pnt(*(endpoint+radius)))
    overlap=float(unintended.mass)
    if not np.isfinite(overlap) or abs(overlap)>1e-18:raise ValueError('Declared return contacts copper outside saved terminal junction windows')
    whole=fuse_all([copper,returned])
    if len(whole.solids)!=1:raise ValueError('Declared finite return does not yield one connected conductor')
    winding,closing,total=float(copper.mass),float(returned.mass),float(whole.mass)
    if not winding*(1-1e-9)<=total<=(winding+closing)*(1+1e-9):
        raise ValueError('Closing fuse lost or invented copper volume;no repair applied')
    return whole,dict(nonterminal_contact_volume_m3=overlap,terminal_audit_window_half_width_m=radius,
        scope='Only audit intersection is clipped at physical terminal windows;no copper/return geometry is removed or repaired.')


def partition_checks(copper,closed,model):
    from netgen.occ import Box,Pnt
    validate_copper_shape(copper);validate_copper_shape(closed)
    regions={value['name']:Box(Pnt(*value['origin_m']),Pnt(*(np.asarray(value['origin_m'])+value['size_m']))) for value in model['stack']+model['magnets']}
    checks={}
    for label,shape in [('winding',copper),('closed_current_copper',closed)]:
        for name,region in regions.items():
            overlap=float((shape*region).mass);distance=float(shape.Distance(region))
            if not np.isfinite([overlap,distance]).all() or abs(overlap)>1e-18 or distance<=0:
                raise ValueError('Actual copper/material overlap or contact requires a user decision;no correction applied')
            checks[label+':'+name]=dict(overlap_m3=overlap,minimum_brep_distance_m=distance)
    for (name,a),(other,b) in itertools.combinations(regions.items(),2):
        overlap=float((a*b).mass)
        if not np.isfinite(overlap) or abs(overlap)>1e-18:raise ValueError('App-defined PM/material regions overlap')
        checks[name+':'+other]=dict(overlap_m3=overlap,minimum_brep_distance_m=float(a.Distance(b)))
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study-work',type=Path,required=True)
    parser.add_argument('--study-receipt',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--fuse-strategy',choices=['pairwise','per-kind'],default='pairwise',
        help='Boolean grouping only; identical primitives/drills, recorded and audited analytically')
    add_thread_option(parser);args=parser.parse_args();origin=args.study_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous finite copper preparations')
    study,snapshot=load_study(origin,args.study_receipt)
    inputs={str(path):sha(path) for path in [origin/'summary.json',origin/'fixture.json',args.study_receipt.resolve()]}
    work.mkdir(parents=True);started=time.monotonic()
    report=dict(status='running',scope=__doc__,input_hashes=inputs,translation_m=study['translation_m'],
        actual_study_work=str(origin),execution=runtime_metadata(),failures=[],
        fuse_strategy=args.fuse_strategy,
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['finite_copper_geometry.py','finite_copper_eligibility.py','finite_copper_circuit.py','winding_oracle.py',
             'finite_copper_grouped.py','audit_copper_union_volume.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        copper,spec=(grouped_build if args.fuse_strategy=='per-kind' else build)(snapshot,study['translation_m'])
        validate_copper_shape(copper)
        # Pairwise OCC fusion has silently dropped copper on a real design, so
        # every build must match the analytic union of its declared primitives.
        report['union_audit']=union_gate(snapshot,study['translation_m'],float(copper.mass));save()
        copper.WriteBrep(str(work/'copper.brep'))
        # The existing builder first rejects any raw/graph span discrepancy.
        # These generated cases therefore have no hidden unlanded physical stub.
        spec.update(full_physical_via_stubs=[],physical_via_spans=len(snapshot['routing']['vias']),
            active_copper_layers=sorted({segment['layer'] for segment in snapshot['routing']['segments']}))
        report.update(geometry=spec,brep_sha256=sha(work/'copper.brep'));save()
        closed,contacts=closed_return(copper,spec,study['closure']['return_path_m'])
        closed.WriteBrep(str(work/'closed-copper-for-partition-audit.brep'))
        report.update(return_contact_audit=contacts,partition_checks=partition_checks(copper,closed,study['model']),
            closed_partition_brep_sha256=sha(work/'closed-copper-for-partition-audit.brep'),closed_partition_volume_m3=float(closed.mass))
        returned=work/'return';returned.mkdir()
        value=dict(status='prepared-physical-dc-return-geometry-only',scope='Explicit declared scenario;not cable CAD or current/force qualification.',
            closure=study['closure'],translation_m=study['translation_m'],input_hashes=inputs,failures=[],command_receipt=report.get('command_receipt'),
            source_snapshots=capture(returned,[Path(__file__)]))
        (returned/'summary.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
        for name,digest in (inputs|study['input_hashes']).items():
            if sha(Path(name))!=digest:raise ValueError('Actual copper study inputs changed during CAD construction')
        for name,entry in report['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Finite copper construction implementation changed')
        report.update(status='completed-finite-copper-geometry-only-unqualified',seconds=time.monotonic()-started);save()
        print(report['status'],report['seconds'],flush=True)
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
