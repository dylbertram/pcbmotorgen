#!/usr/bin/env python3
"""Isolated finer-curvature control of accepted actual source sections/fields.

Both source runs and all eligible section reports must pass before comparison.
Preserves the 2% resistance/local/field gates and near-zero floors. No failed
coarse-area report is admitted as a reference, and no force is qualified here.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_dc_section_refinement import compare_sections,load_sections
from audit_finite_dc_controls import MIXED,load,resistance_check
from audit_linear_dc_near_field import relative
from compare_reduced_fields import completed_receipt
from finite_tetra_current_field import tetrahedron_field
from post_project_force import sha
from source_snapshot import capture


def isolated_curvature(first,second):
    if first['version']!=second['version'] or first['input_hashes']!=second['input_hashes'] or first['geometry']!=second['geometry']:
        raise ValueError('Curvature control changed engine or physical copper/return')
    left,right=first['request'],second['request']
    if set(left)!=set(right) or {key for key in left if left[key]!=right[key]}!={'curvature_safety'}:
        raise ValueError('Only curvature safety may change')
    if not 2<left['curvature_safety']<right['curvature_safety'] or second['mesh_elements']<=first['mesh_elements']:
        raise ValueError('Independently finer numerical curvature required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['first-work','second-work','first-sections','second-sections','near-field-work','source-export','work']:
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous curvature controls')
    first=load(args.first_work.resolve(),MIXED);second=load(args.second_work.resolve(),MIXED);isolated_curvature(first,second)
    first_sections,_=load_sections(args.first_sections,args.first_work)
    second_sections,_=load_sections(args.second_sections,args.second_work)
    sections=compare_sections(first_sections,second_sections)
    near=json.loads((args.near_field_work/'summary.json').read_text());export=json.loads((args.source_export/'summary.json').read_text())
    for report in [near,export]:completed_receipt(report)
    if near['status']!='passed-sampled-linear-near-field-controls-only' or near['failures'] or export['status']!='passed-affine-rt0-source-export-only':
        raise ValueError('Accepted exact source export and fixed-probe integration controls required')
    if export['source_work']!=str(args.second_work.resolve()):raise ValueError('Curvature export uses a different source')
    first_summary=args.first_work.resolve()/'summary.json';second_summary=args.second_work.resolve()/'summary.json'
    if near['input_hashes'].get(str(first_summary))!=sha(first_summary) or export['input_hashes'].get(str(second_summary))!=sha(second_summary):
        raise ValueError('Near-field or export belongs to a different source run')
    paths=[first_summary,second_summary,args.first_sections.resolve(),args.second_sections.resolve(),
        args.near_field_work.resolve()/'summary.json',args.source_export.resolve()/'summary.json',args.source_export.resolve()/'rt0-source.npz']
    inputs={str(p):sha(p) for p in paths}|near['input_hashes']|export['input_hashes']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Curvature-control evidence changed')
    with np.load(args.source_export/'rt0-source.npz',allow_pickle=False) as saved:
        cells=saved['vertices_m'][saved['cells']];mean=saved['mean_current_a_m2'];slope=saved['radial_slope_a_m3']
    points=np.asarray([probe['point_m'] for probe in near['probes']]);actual=tetrahedron_field(points,cells,mean,radial_slope=slope)/export['effective_loop_current_a']
    errors=relative(np.asarray(near['analytical_field_t_per_loop_a']),actual);resistance=resistance_check(first,second,.02)
    failures=[item['label'] for item in sections if not item['passed']]
    if not resistance['passed']:failures.append('resistance')
    failures.extend('field:'+near['probes'][i]['label'] for i,e in enumerate(errors) if not np.isfinite(e) or e>.02)
    work.mkdir(parents=True)
    report=dict(status='failed-isolated-curvature-controls' if failures else 'passed-isolated-curvature-controls-only',scope=__doc__,
        input_hashes=inputs,curvature_safety=[first['request']['curvature_safety'],second['request']['curvature_safety']],
        resistance_check=resistance,sections=sections,probes=near['probes'],field_relative_errors=errors.tolist(),failures=failures,
        relative_refinement_gate=.02,field_floor_t_per_loop_a=1e-12,
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
            ['audit_dc_section_refinement.py','audit_finite_dc_controls.py','finite_tetra_current_field.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Curvature-control input changed during evaluation')
    (work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(report['status'],resistance,'max field',float(max(errors)),flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
