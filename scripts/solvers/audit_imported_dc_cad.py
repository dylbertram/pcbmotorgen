#!/usr/bin/env python3
"""Independent BRep queries of saved physical via gaps, bores and stub sections.

Geometry control only. Does not qualify a DC solution, material or force.
"""
import argparse
import json
import os
from pathlib import Path
import time

from compare_reduced_fields import completed_receipt
from finite_copper_geometry import dimensions
from prepare_imported_dc_source import via_records
from post_project_force import sha
from solver_threads import add_thread_option, threaded_main
from source_snapshot import capture


def checks(shape,snapshot,geometry):
    from netgen.occ import Pnt,Dir,Cylinder
    from finite_copper_geometry import fuse_all
    spec=dimensions(snapshot);records=via_records(snapshot);gaps=[];bores=[]
    for (x,y),record in records.items():
        for span in record['spans']:
            bores.append(Cylinder(Pnt(x,y,span['low']),Dir(0,0,1),spec['via_inner_radius_m'],span['high']-span['low']))
        for first,second in zip(record['spans'][:-1],record['spans'][1:]):
            height=(second['low']-first['high'])/3;low=first['high']+height
            gaps.append(Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_outer_radius_m']*1.05,height))
    gap_volume=float((shape*fuse_all(gaps)).mass) if gaps else 0.
    bore_volume=float((shape*fuse_all(bores)).mass) if bores else 0.
    stub_records=[];thickness=min(layer['thickness_m'] for layer in spec['layers'])
    for record in geometry['full_physical_via_stubs']:
        raw=record['full_centreplane_range_m'];landed=record['electrical_landing_range_m']
        if landed is None:raise ValueError('Unlanded whole via requires separate geometric/source controls')
        for lo,hi in [(raw[0],landed[0]),(landed[1],raw[1])]:
            if hi<=lo:continue
            if hi-lo<=4*thickness:raise ValueError('No isolated full-barrel stub section')
            x,y=record['position_m'];mid=(lo+hi)/2
            window=Cylinder(Pnt(x,y,mid-thickness/2),Dir(0,0,1),spec['via_outer_radius_m']*1.1,thickness)
            actual=float((shape*window).mass);expected=spec['via_barrel_area_m2']*thickness
            error=abs(actual/expected-1)
            stub_records.append(dict(position_m=[x,y,mid],actual_volume_m3=actual,expected_volume_m3=expected,
                                     relative_error=error,limit=1e-9,passed=error<=1e-9))
    return dict(gap_windows=len(gaps),gap_copper_volume_m3=gap_volume,bore_spans=len(bores),
                bore_copper_volume_m3=bore_volume,stub_sections=stub_records,
                passed=gap_volume==0. and bore_volume==0. and all(record['passed'] for record in stub_records))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--geometry-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);add_thread_option(parser);args=parser.parse_args()
    work=args.work.resolve();origin=args.geometry_work.resolve()
    if work.exists():parser.error('Preserve prior CAD audits')
    summary=origin/'summary.json';geometry=json.loads(summary.read_text());completed_receipt(geometry)
    if geometry['status']!='completed-finite-copper-geometry-only-unqualified':raise ValueError('Incomplete exact geometry')
    fixture=[Path(path) for path in geometry['input_hashes'] if path.endswith('/fixture.json')]
    if len(fixture)!=1:raise ValueError('Unique actual imported geometry snapshot required')
    fixture=fixture[0];brep=origin/'copper.brep'
    if sha(fixture)!=geometry['input_hashes'][str(fixture)] or sha(brep)!=geometry['brep_sha256']:
        raise ValueError('Saved physical geometry changed')
    inputs={str(path):sha(path) for path in [summary,fixture,brep]};work.mkdir(parents=True);start=time.monotonic()
    report=dict(status='running',scope=__doc__,input_hashes=inputs,
        source_snapshots=capture(work,[Path(__file__),Path(__file__).with_name('prepare_imported_dc_source.py'),
            Path(__file__).with_name('finite_copper_geometry.py')]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        from netgen.occ import OCCGeometry
        report['checks']=checks(OCCGeometry(str(brep)).shape,json.loads(fixture.read_text()),geometry['geometry'])
        if not report['checks']['passed']:raise ValueError('Saved via gap/bore/stub CAD controls failed')
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Saved CAD input changed during audit')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Saved CAD audit implementation changed')
        report.update(status='passed-imported-via-gap-bore-stub-cad-only',seconds=time.monotonic()-start);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-start);save();raise


if __name__=='__main__':threaded_main(main)
