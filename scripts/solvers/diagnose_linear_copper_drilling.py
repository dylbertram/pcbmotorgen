#!/usr/bin/env python3
"""Read-only drill-order diagnostic on the exact declared copper primitives.

Fuses unchanged parts by kind, then subtracts the unchanged fused bores once.
This changes Boolean operation ordering only. No tolerance, geometry healing,
material shift or downstream-use CAD is produced. A diagnostic success does
not qualify current, force, topology or the production builder.
"""
import argparse
import json
from pathlib import Path
import time

from audit_copper_union_volume import primitives,union_estimate
from finite_copper_geometry import dimensions,fuse_all
from finite_copper_grouped import build_groups,kind
from post_project_force import sha
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-work',type=Path,required=True)
    parser.add_argument('--copper-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    study=args.study_work.resolve();copper=args.copper_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous drill diagnostics')
    inputs={str(p):sha(p) for p in [study/'fixture.json',study/'summary.json',copper/'summary.json']}
    fixture=json.loads((study/'fixture.json').read_text())
    shift=json.loads((copper/'summary.json').read_text())['translation_m']
    from netgen.occ import Cylinder,Pnt,Dir
    started=time.monotonic();work.mkdir(parents=True)
    report=dict(status='running',scope=__doc__,input_hashes=inputs,stages=[],parts={},
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
            ['finite_copper_grouped.py','finite_copper_geometry.py','audit_copper_union_volume.py']]]))
    def checkpoint(stage):
        report['stages'].append(dict(stage=stage,seconds=time.monotonic()-started))
        (work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(stage,round(time.monotonic()-started,3),flush=True)
    checkpoint('start')
    try:
        spec=dimensions(fixture);pieces,groups,analytic=build_groups(fixture,shift)
        _,drills=primitives(fixture,shift);names=sorted({kind(g['label']) for g in groups})
        checkpoint('exact-pieces-built')
        parts=[]
        for name in names:
            part=fuse_all([p for p,g in zip(pieces,groups) if kind(g['label'])==name])
            report['parts'][name]=dict(volume_m3=float(part.mass),solids=len(part.solids));parts.append(part)
            checkpoint('part-fused:'+name)
        whole=fuse_all(parts)
        report['undrilled']=dict(volume_m3=float(whole.mass),solids=len(whole.solids))
        checkpoint('undrilled-whole-fused')
        bore=fuse_all([Cylinder(Pnt(d['centre'][0],d['centre'][1],d['z'][0]),Dir(0,0,1),
            spec['via_inner_radius_m'],d['z'][1]-d['z'][0]) for d in drills])
        report['bores']=dict(count=len(drills),volume_m3=float(bore.mass),solids=len(bore.solids))
        checkpoint('bores-fused-before-single-cut')
        drilled=whole-bore
        report['drilled']=dict(volume_m3=float(drilled.mass),solids=len(drilled.solids))
        checkpoint('single-drill-cut-complete')
        estimate,error=union_estimate(analytic,drills,4000)
        report['analytic']=dict(volume_m3=estimate,standard_error_m3=error,
            relative_cad_difference=float(abs(drilled.mass/estimate-1)))
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Physical diagnostic input changed')
        report['status']='completed-drill-order-diagnostic-only'
        checkpoint('done')
    except BaseException as error:
        report.update(status='failed-drill-order-diagnostic',error=str(error));checkpoint('failed');raise


if __name__=='__main__':main()
