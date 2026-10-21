#!/usr/bin/env python3
"""Read-only finite-copper/magnetic-envelope decision audit, not a correction.

Reloads the accepted copper BRep and its original rectangular magnetic model.
No geometry, material assignment, current solution or model input is changed.
The optional picture projects saved bottom-layer traces/pads; exact intersection
volumes come from the BRep boolean, not from the picture or sampled centre lines.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def layer_intervals(spec, shift):
    shift = np.asarray(shift, dtype=float)
    if shift.shape != (3,) or not np.isfinite(shift).all():
        raise ValueError('Need an explicit finite rigid translation')
    result = []
    for layer in spec['layers']:
        centre = float(layer['centre_z_m']) + shift[2]
        thickness = float(layer['thickness_m'])
        if not np.isfinite([centre, thickness]).all() or thickness <= 0:
            raise ValueError('Invalid saved layer dimensions')
        result.append(dict(layer=layer['layer'], centre_z_m=float(centre),
                           low_z_m=float(centre-thickness/2), high_z_m=float(centre+thickness/2),
                           thickness_m=thickness))
    if not result:
        raise ValueError('Missing saved copper layers')
    return result


def overlap_depth(first, second):
    values = np.asarray([*first, *second], dtype=float)
    if not np.isfinite(values).all() or first[1] < first[0] or second[1] < second[0]:
        raise ValueError('Invalid physical interval')
    return max(0., min(first[1], second[1])-max(first[0], second[0]))


def rectangular_bounds(layer):
    low = np.asarray(layer['origin_m'], dtype=float)
    size = np.asarray(layer['size_m'], dtype=float)
    if low.shape != (3,) or size.shape != (3,) or not np.isfinite([low, size]).all() or np.any(size <= 0):
        raise ValueError('Need an explicit positive rectangular magnetic envelope')
    return low, low+size


def bounds(shape):
    # OCCT bounds include tolerances. They are not physical clearance values.
    return [[float(c) for c in point] for point in shape.bounding_box]


def add_clipped(axes, patch, clip):
    # add_patch can install the axes clip when a rectangular clip is optimized
    # to a clip box. Set the physical-envelope clip only after insertion.
    axes.add_patch(patch)
    patch.set_clip_path(clip)


def picture(path, fixture, shift, intervals, layer, volume):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon, Rectangle
    from winding_oracle import edge_points

    low, high = rectangular_bounds(layer)
    affected = {x['layer'] for x in intervals
                if overlap_depth((x['low_z_m'], x['high_z_m']), (low[2], high[2])) > 0}
    fig, (plan, section) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={'width_ratios': [2, 1]})
    fig.patch.set_facecolor('white')
    clip = Rectangle(low[:2]*1e3, *(high[:2]-low[:2])*1e3, facecolor='#eef2f6', edgecolor='#64748b')
    plan.add_patch(clip)
    width = fixture['sim']['min_trace_m']*1e3
    radius = (fixture['sim']['min_via_drill_m']/2+fixture['sim']['min_via_annular_ring_m'])*1e3
    hole = fixture['sim']['min_via_drill_m']/2*1e3
    vias = set()
    for network in fixture['networks']:
        for edge in network['edges']:
            geometry = edge['geometry']
            points = (edge_points(edge, fixture['sim'], fixture['geometry_hints'])+shift)*1e3
            if geometry['kind'] == 'via':
                if affected.intersection(geometry['layers']):
                    vias.add(tuple(points[0, :2]))
                continue
            if geometry['kind'] != 'trace' or geometry['layer'] not in affected:
                continue
            for a, b in zip(points[:-1, :2], points[1:, :2]):
                vector = b-a
                length = np.linalg.norm(vector)
                if length <= 0:
                    raise ValueError('Zero-length saved trace in decision picture')
                normal = np.array([-vector[1], vector[0]])/length*width/2
                patch = Polygon([a+normal, b+normal, b-normal, a-normal], color='#dc2626', linewidth=0)
                add_clipped(plan, patch, clip)
            for point in points[:, :2]:
                patch = Circle(point, width/2, color='#dc2626', linewidth=0)
                add_clipped(plan, patch, clip)
    for point in sorted(vias):
        patch = Circle(point, radius, color='#dc2626', linewidth=0)
        add_clipped(plan, patch, clip)
    # The original finite CAD drills the whole copper union, not just pads.
    for point in sorted(vias):
        patch = Circle(point, hole, color='#eef2f6', linewidth=0)
        add_clipped(plan, patch, clip)
    plan.set(xlim=(low[0]*1e3-1, high[0]*1e3+1), ylim=(low[1]*1e3-1, high[1]*1e3+1),
             xlabel='X (mm)', ylabel='Y (mm)', title='Intersecting-layer copper projection inside ferrite footprint')
    plan.set_aspect('equal')
    bottom = min(intervals, key=lambda x: x['low_z_m'])
    section.add_patch(Rectangle((0, low[2]*1e6), 1, (high[2]-low[2])*1e6, color='#cbd5e1'))
    section.add_patch(Rectangle((.3, bottom['low_z_m']*1e6), .4, bottom['thickness_m']*1e6, color='#d97706'))
    a, b = max(bottom['low_z_m'], low[2]), min(bottom['high_z_m'], high[2])
    if b > a:
        section.add_patch(Rectangle((.3, a*1e6), .4, (b-a)*1e6, color='#dc2626'))
    section.axhline(high[2]*1e6, color='#475569', linestyle='--', linewidth=1)
    section.text(.5, bottom['high_z_m']*1e6+10, f"{bottom['thickness_m']*1e6:g} µm copper", ha='center')
    section.text(.5, (a+b)*.5e6-30, f'{(b-a)*1e6:.1f} µm overlap', ha='center', color='#991b1b')
    section.text(.5, low[2]*1e6+35, 'Ferrite envelope', ha='center')
    section.set(xlim=(0, 1), ylim=(low[2]*1e6-20, bottom['high_z_m']*1e6+55), xticks=[],
                ylabel='Z (µm), nominal PCB-bottom reference = 0', title='Local section through a lower copper trace')
    fig.suptitle(f'Unresolved copper/ferrite intersection: {volume*1e9:.6f} mm³', color='#111827')
    fig.text(.5, .015, 'Projection is a location aid; exact BRep boolean supplies volume. No correction applied.', ha='center', color='#475569')
    fig.tight_layout(rect=(0, .09, 1, .94))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-work', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--picture', action='store_true')
    args = parser.parse_args()
    origin, work = args.geometry_work.resolve(), args.work.resolve()
    if work.exists():
        parser.error('Preserve earlier decision evidence')
    source = json.loads((origin/'summary.json').read_text())
    completed_receipt(source)
    if source['status'] != 'completed-finite-copper-geometry-only-unqualified':
        raise ValueError('Need the original accepted finite copper geometry')
    inputs = {str(origin/'summary.json'): sha(origin/'summary.json'), str(origin/'copper.brep'): source['brep_sha256'], **source['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Original physical input changed: '+path)
    candidates = [(Path(p), json.loads(Path(p).read_text())) for p in source['input_hashes'] if Path(p).name == 'summary.json']
    models = [(p, s) for p, s in candidates if 'model' in s]
    if len(models) != 1:
        raise ValueError('Ambiguous original magnetic model')
    model_path, model_source = models[0]
    completed_receipt(model_source)
    if model_source.get('failures') != []:
        raise ValueError('Original magnetic model is not accepted')
    model = model_source['model']
    fixture_paths = [Path(p) for p in source['input_hashes'] if Path(p).name == 'fixture.json']
    if len(fixture_paths) != 1:
        raise ValueError('Missing original saved copper export')
    fixture = json.loads(fixture_paths[0].read_text())
    intervals = layer_intervals(source['geometry'], source['translation_m'])
    from netgen.occ import OCCGeometry, Box, Pnt
    started = time.monotonic()
    copper = OCCGeometry(str(origin/'copper.brep')).shape
    if abs(float(copper.mass)/source['geometry']['volume_m3']-1) > 1e-10:
        raise ValueError('Reloaded finite copper volume changed')
    work.mkdir(parents=True)
    report = {'status': 'running', 'scope': __doc__, 'input_hashes': inputs, 'model_source': str(model_path),
              'source_snapshots': capture(work, [Path(__file__), Path(__file__).with_name('winding_oracle.py')]),
              'coordinate_convention': model['coordinate_convention'], 'layers': intervals,
              'copper_volume_m3': float(copper.mass), 'copper_occt_tolerance_bounds_m': bounds(copper),
              'bounds_warning': 'OCCT bounding boxes include tolerances; nominal layer intervals, not box padding, define physical Z extents.',
              'magnetic_intersections': {}, 'decision_required': True, 'geometry_changed': False}
    for layer in model['stack']:
        if layer['mu_r'] <= 1:
            continue
        low, high = rectangular_bounds(layer)
        intersection = copper*Box(Pnt(*low), Pnt(*high))
        volume = float(intersection.mass)
        original = source['nominal_magnetic_overlap_m3'][layer['name']]
        if abs(volume-original) > max(1e-18, 1e-8*abs(original)):
            raise ValueError('Original measured overlap was not reproduced')
        entry = {'material': layer['material'], 'origin_m': low.tolist(), 'size_m': (high-low).tolist(),
                 'overlap_m3': volume, 'overlap_mm3': volume*1e9,
                 'overlap_fraction_of_copper': volume/float(copper.mass),
                 'overlap_fraction_of_magnetic_envelope': volume/float(np.prod(high-low)),
                 'intersection_solid_components': len(intersection.solids),
                 'component_warning': 'Intersection components are not winding-network components.',
                 'nominal_layer_depth_intersections': [dict(layer=x['layer'], depth_m=overlap_depth((x['low_z_m'], x['high_z_m']), (low[2], high[2]))) for x in intervals],
                 'downward_displacement_from_nominal_layer_extents_m': max(0., float(high[2])-min(x['low_z_m'] for x in intervals)),
                 'clearance_warning': 'Displacement is a sufficient contact-only candidate from nominal layer extents, not an approved dielectric clearance or design change.'}
        if volume > 0:
            entry['intersection_occt_tolerance_bounds_m'] = bounds(intersection)
            if args.picture:
                image = work/(layer['name']+'-overlap.png')
                picture(image, fixture, np.asarray(source['translation_m']), intervals, layer, volume)
                entry['picture'] = str(image)
                entry['picture_sha256'] = sha(image)
        report['magnetic_intersections'][layer['name']] = entry
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Physical input changed during read-only audit')
    report.update(status='completed-read-only-overlap-decision-audit', seconds=time.monotonic()-started)
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(report['status'], json.dumps(report['magnetic_intersections'], indent=2), flush=True)


if __name__ == '__main__':
    main()
