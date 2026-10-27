#!/usr/bin/env python3
"""Isolated source-mesh or drive-length comparison at fixed accepted field probes.

Compares exact affine RT0 cell-face fields from independent completed source
controls at the identical predetermined near-copper and app-region probes.
No force, interpolation, every-point or independent magnetic-solve claim.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_finite_dc_controls import MIXED,load,validate_control
from audit_linear_dc_near_field import FLOOR,relative
from compare_reduced_fields import completed_receipt
from finite_tetra_current_field import tetrahedron_field
from post_project_force import sha
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-work',type=Path,required=True)
    parser.add_argument('--source-work',type=Path,required=True)
    parser.add_argument('--kind',choices=['mesh','port'],required=True)
    parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    reference=args.reference_work.resolve();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous source-field controls')
    baseline=json.loads((reference/'summary.json').read_text());source=json.loads((origin/'summary.json').read_text())
    for report in [baseline,source]:completed_receipt(report)
    if baseline['status']!='passed-sampled-linear-near-field-controls-only' or baseline['failures']:
        raise ValueError('Whole accepted fixed-probe integration control required')
    if source['status']!='passed-affine-rt0-source-export-only':raise ValueError('Exact accepted source export required')
    baseline_exports=[Path(p) for p in baseline['input_hashes'] if p.endswith('/rt0-source.npz')]
    if len(baseline_exports)!=1:raise ValueError('Unique baseline current export required')
    baseline_export=json.loads(baseline_exports[0].with_name('summary.json').read_text());completed_receipt(baseline_export)
    first=load(Path(baseline_export['source_work']),MIXED);second=load(Path(source['source_work']),MIXED)
    validate_control(first,second,args.kind)
    if first['request']['curvature_safety']!=second['request']['curvature_safety']:
        raise ValueError('Isolated source control cannot change curvature')
    paths=[reference/'summary.json',origin/'summary.json',origin/'rt0-source.npz',baseline_exports[0].with_name('summary.json')]
    inputs={str(p):sha(p) for p in paths}|baseline['input_hashes']|source['input_hashes']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Accepted source-field evidence changed')
    points=np.asarray([probe['point_m'] for probe in baseline['probes']]);expected=np.asarray(baseline['analytical_field_t_per_loop_a'])
    with np.load(origin/'rt0-source.npz',allow_pickle=False) as saved:
        cells=saved['vertices_m'][saved['cells']];mean=saved['mean_current_a_m2'];slope=saved['radial_slope_a_m3']
    started=time.monotonic();work.mkdir(parents=True)
    report=dict(status='running',scope=__doc__,kind=args.kind,input_hashes=inputs,probes=baseline['probes'],
        field_floor_t_per_loop_a=FLOOR,relative_refinement_gate=.02,
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
            ['audit_linear_dc_near_field.py','audit_finite_dc_controls.py','finite_tetra_current_field.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        actual=tetrahedron_field(points,cells,mean,radial_slope=slope)/source['effective_loop_current_a'];errors=relative(expected,actual)
        report.update(analytical_field_t_per_loop_a=actual.tolist(),relative_errors=errors.tolist(),
            failures=[baseline['probes'][i]['label'] for i,error in enumerate(errors) if not np.isfinite(error) or error>.02])
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Source-field evidence changed during control')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Source-field implementation changed during control')
        report.update(status='failed-sampled-source-field-refinement' if report['failures'] else 'passed-sampled-source-field-refinement-only',seconds=time.monotonic()-started);save()
        if report['failures']:raise ValueError('Fixed-probe source-field refinement failed unchanged2%gate')
    except BaseException as error:
        report.update(status='failed-sampled-source-field-refinement',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
