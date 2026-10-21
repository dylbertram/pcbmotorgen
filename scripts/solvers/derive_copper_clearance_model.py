#!/usr/bin/env python3
"""Construct explicitly approved, disjoint DC-study material geometry only.

Moves the whole saved backplane stack to an approved copper-surface clearance.
Never changes copper/magnets, source projects or a user's original model files.
Does not solve magnetic fields or qualify a B-H law, force or temperature.
"""
import argparse
from copy import deepcopy
import itertools
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_copper_magnetic_overlap import layer_intervals, rectangular_bounds
from audit_finite_dc_controls import MIXED, load
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def approved_model(model, intervals, approval):
    required = ['preserve_copper', 'preserve_magnets', 'preserve_layer_thicknesses',
                'preserve_internal_stack_gaps', 'preserve_root_files']
    if approval.get('status') != 'user-approved-derived-geometry' or any(approval.get(k) is not True for k in required):
        raise ValueError('Explicit preservation and geometry approval required')
    if approval.get('source_project_sha256') != model['source_sha256'] or approval.get('source_version_index') != model['version_index']:
        raise ValueError('Approval applies to a different project/version')
    if approval.get('move_policy') != 'translate-entire-backplane-stack-downward':
        raise ValueError('This runner only implements the explicitly approved whole-stack move')
    clearance = approval['copper_to_ferrite_clearance_m']
    if isinstance(clearance, bool) or not np.isfinite(clearance) or clearance < 0:
        raise ValueError('Explicit nonnegative finite physical clearance required')
    if not intervals or not model['stack']:
        raise ValueError('Missing saved copper/stack geometry')
    magnetic = [x for x in model['stack'] if x['mu_r'] > 1]
    if not magnetic:
        raise ValueError('Missing magnetic region')
    top = max(float(rectangular_bounds(x)[1][2]) for x in magnetic)
    copper_low = min(x['low_z_m'] for x in intervals)
    delta = float(copper_low-clearance-top)
    if delta > 0:
        raise ValueError('Approval is downward-only; refuse an automatic upward move')
    result = deepcopy(model)
    for region in result['stack']:
        rectangular_bounds(region)
        region['origin_m'][2] += delta
    return result, delta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-work', type=Path, required=True)
    parser.add_argument('--current-work', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    origin, current_work, approval_path, work = [p.resolve() for p in
        [args.geometry_work, args.current_work, args.approval, args.work]]
    if work.exists():
        parser.error('Preserve earlier derived studies')
    source = json.loads((origin/'summary.json').read_text())
    completed_receipt(source)
    if source['status'] != 'completed-finite-copper-geometry-only-unqualified':
        raise ValueError('Need the accepted original finite copper BRep')
    current = load(current_work, MIXED)
    if current['input_hashes'].get(str(origin/'copper.brep')) != source['brep_sha256']:
        raise ValueError('Current source does not use this saved copper')
    approval = json.loads(approval_path.read_text())
    models = [Path(p) for p in source['input_hashes'] if Path(p).name == 'summary.json' and
              'model' in json.loads(Path(p).read_text())]
    if len(models) != 1:
        raise ValueError('Ambiguous original magnetic model')
    model_path = models[0]
    model_source = json.loads(model_path.read_text())
    completed_receipt(model_source)
    if model_source.get('failures') != []:
        raise ValueError('Unaccepted source model')
    inputs = {str(origin/'summary.json'): sha(origin/'summary.json'),
              str(origin/'copper.brep'): source['brep_sha256'],
              str(current_work/'summary.json'): sha(current_work/'summary.json'),
              str(current_work/'closed-copper.brep'): current['brep_sha256'],
              str(current_work/'dc-current-potential.sol'): current['solution_sha256'],
              str(approval_path): sha(approval_path), **source['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Original input changed: '+path)
    model, delta = approved_model(model_source['model'], layer_intervals(source['geometry'], source['translation_m']), approval)
    from netgen.occ import OCCGeometry, Box, Pnt
    started = time.monotonic()
    original_copper = OCCGeometry(str(origin/'copper.brep')).shape
    closed_copper = OCCGeometry(str(current_work/'closed-copper.brep')).shape
    regions = {}
    for region in model['stack']:
        low, high = rectangular_bounds(region)
        regions[region['name']] = Box(Pnt(*low), Pnt(*high))
    checks = {}
    for label, copper in [('saved_copper', original_copper), ('closed_current_copper', closed_copper)]:
        for name, region in regions.items():
            overlap = float((copper*region).mass)
            distance = float(copper.Distance(region))
            if abs(overlap) > 1e-18 or not np.isfinite(distance) or distance < 0:
                raise ValueError('Approved copper/material partition failed')
            if next(x for x in model['stack'] if x['name'] == name)['mu_r'] > 1:
                target = approval['copper_to_ferrite_clearance_m']
                if distance+1e-10 < target:
                    raise ValueError('Exact BRep clearance is smaller than approved separation')
            checks[label+':'+name] = {'overlap_m3': overlap, 'minimum_brep_distance_m': distance}
    for first, second in itertools.combinations(model['stack'], 2):
        a, b = regions[first['name']], regions[second['name']]
        overlap = float((a*b).mass)
        if abs(overlap) > 1e-18:
            raise ValueError('Stack regions overlap after approved rigid translation')
        old_a, old_b = [next(x for x in model_source['model']['stack'] if x['name'] == y['name']) for y in [first, second]]
        old_shapes = [Box(Pnt(*rectangular_bounds(y)[0]), Pnt(*rectangular_bounds(y)[1])) for y in [old_a, old_b]]
        before, after = float(old_shapes[0].Distance(old_shapes[1])), float(a.Distance(b))
        if abs(before-after) > 1e-10:
            raise ValueError('Internal stack spacing changed')
        checks[first['name']+':'+second['name']] = {'overlap_m3': overlap, 'original_distance_m': before, 'derived_distance_m': after}
    for before, after in zip(model_source['model']['stack'], model['stack']):
        actual = float(regions[after['name']].mass)
        if abs(actual/float(np.prod(before['size_m']))-1) > 1e-10:
            raise ValueError('Layer volume/thickness changed')
    work.mkdir(parents=True)
    report = {'status': 'completed-approved-disjoint-material-geometry-only', 'scope': __doc__,
              'model': model, 'model_delta_z_m': delta, 'approval': approval, 'input_hashes': inputs,
              'current_source_work': str(current_work), 'current_source_reused_without_new_solve': True,
              'geometry_checks': checks, 'failures': [],
              'remaining': ['broader local current-source coverage', 'coupled zero-current/linear/nonlinear field controls',
                            'mesh/domain/quadrature and independent force checks', 'qualified app integration'],
              'source_snapshots': capture(work, [Path(__file__), Path(__file__).with_name('audit_copper_magnetic_overlap.py')]),
              'seconds': time.monotonic()-started}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Original input changed during derived geometry construction')
    (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(report['status'], 'stack Z translation', delta, json.dumps(checks, indent=2), flush=True)


if __name__ == '__main__':
    main()
