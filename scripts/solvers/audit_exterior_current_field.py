#!/usr/bin/env python3
"""Source-only exterior finite-current integration pilot; no material coupling.

Two deterministic points lie 1 and 2 mm below the entire exact saved source.
Their XY positions come from the first/last lowest-layer eligible trace labels.
No ferrite, housing, material clearance, force or app admission is implied.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_finite_current_source_field import volume_field
from compare_reduced_fields import completed_receipt
from finite_tetra_current_field import tetrahedron_field
from post_project_force import sha
from source_snapshot import capture


def observation_points(sections,source_lowest_z):
    traces=[value for value in sections if value['label'].startswith('trace:')]
    if not traces or not np.isfinite(source_lowest_z):raise ValueError('Finite source bounds and eligible actual traces required')
    lowest=min(value['centre_m'][2] for value in traces)
    eligible=sorted((value for value in traces if abs(value['centre_m'][2]-lowest)<1e-12),key=lambda value:value['label'])
    selected=[eligible[0],eligible[-1]]
    points=np.array([[*value['centre_m'][:2],source_lowest_z-gap] for value,gap in zip(selected,[.001,.002])])
    if not np.isfinite(points).all():raise ValueError('Finite physical observation coordinates required')
    return points,[value['label'] for value in selected]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--section-audit',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    origin=args.source_work.resolve();section_path=args.section_audit.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve prior exterior source pilots')
    source=json.loads((origin/'summary.json').read_text());sections=json.loads(section_path.read_text())
    for entry in [source,sections]:completed_receipt(entry)
    if source['status']!='passed-affine-rt0-source-export-only':raise ValueError('Exact affine RT0 source export required')
    if sections['status']!='passed-finite-dc-all-eligible-winding-sections-only' or sections['failures'] or len(sections['sections'])!=sections['expected_sections']:
        raise ValueError('Completed expanded winding section audit required')
    if source['source_work']!=sections['source_work'] or sections['source_summary_sha256']!=source['input_hashes'][str(Path(source['source_work'])/'summary.json')]:
        raise ValueError('Source/sections current-state binding changed')
    archive=origin/'rt0-source.npz';inputs={str(origin/'summary.json'):sha(origin/'summary.json'),str(section_path):sha(section_path),str(archive):source['archive_sha256'],**source['input_hashes']}
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Exterior source pilot inputs changed')
    with np.load(archive,allow_pickle=False) as saved:
        vertices=saved['vertices_m'];cells=vertices[saved['cells']]
        mean=saved['mean_current_a_m2'];slope=saved['radial_slope_a_m3']
    points,labels=observation_points(sections['sections'],float(vertices[:,2].min()))
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('Source quadrature engine changed')
    work.mkdir(parents=True);started=time.monotonic()
    report=dict(status='running',scope=__doc__,input_hashes=inputs,points_m=points.tolist(),trace_labels=labels,
        observation_selection='First/last lowest-layer eligible trace label XY;1/2mm below entire source minimumZ. No material geometry.',
        effective_loop_current_a=source['effective_loop_current_a'],levels={},failures=[],
        refinement_limit=.02,agreement_limit=.05,field_floor_t=1e-12,
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in ['audit_finite_current_source_field.py','finite_tetra_current_field.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        now=time.monotonic();exact=tetrahedron_field(points,cells,mean,radial_slope=slope)
        report.update(analytical_field_t=exact.tolist(),analytical_seconds=time.monotonic()-now);save()
        print('exterior-analytical-complete',report['analytical_seconds'],flush=True)
        for order in [2,4,6]:
            now=time.monotonic();field=volume_field(points,cells,mean,slope,ng.IntegrationRule(ng.ET.TET,order))
            report['levels'][str(order)]=dict(field_t=field.tolist(),seconds=time.monotonic()-now);save()
            print('exterior-volume-order',order,report['levels'][str(order)]['seconds'],flush=True)
        middle=np.asarray(report['levels']['4']['field_t']);fine=np.asarray(report['levels']['6']['field_t'])
        scale=np.maximum(np.linalg.norm(fine,axis=1),1e-12)
        refinement=np.linalg.norm(middle-fine,axis=1)/scale;agreement=np.linalg.norm(exact-fine,axis=1)/scale
        report.update(refinement_relative=refinement.tolist(),agreement_relative=agreement.tolist(),
            analytical_field_t_per_loop_a=(exact/source['effective_loop_current_a']).tolist())
        if not np.isfinite([refinement,agreement]).all() or np.max(refinement)>.02:report['failures'].append('Source-volume quadrature refinement fails2%gate')
        if not np.isfinite(agreement).all() or np.max(agreement)>.05:report['failures'].append('Analytical/volume source integration fails5%gate')
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Exterior source pilot inputs changed during integration')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Exterior field implementation changed')
        report.update(status=('failed' if report['failures'] else 'passed')+'-two-exterior-source-points-only',seconds=time.monotonic()-started);save()
        if report['failures']:raise ValueError('Exterior field pilot gates failed')
    except BaseException as error:
        report.update(status='failed-two-exterior-source-points-only',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
