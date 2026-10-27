#!/usr/bin/env python3
"""Offline exact imported-copper/declared-return geometry, no magnetic result.

Uses actual routing primitives and full physical via spans, never graph chord
solids or graph-only landed barrel lengths. Original designs/materials stay
unchanged. New source geometry is not admitted to the app by this preparation.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from closed_winding import build as closed_graph
from compare_reduced_fields import completed_receipt
from finite_circular_copper import chord_control, solid as arc_solid
from finite_copper_geometry import dimensions, trace_solid, fuse_all
from post_project_force import sha
from solver_threads import add_thread_option, threaded_main, runtime_metadata
from source_snapshot import capture
from winding_oracle import layer_z, resistances, unit_currents


def via_records(snapshot):
    """Full raw barrel spans and saved pad planes, including unlanded stubs."""
    spec = dimensions(snapshot);layers = spec['layers'];records = {}
    for via in snapshot['routing']['vias']:
        lo, hi = sorted([via['from_layer'], via['to_layer']])
        if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi < len(layers):
            raise ValueError('Invalid full physical via span')
        xy = (via['position']['x']*1e-3, via['position']['y']*1e-3)
        record = records.setdefault(xy, dict(intervals=[], layers=set(), nets=set()))
        pad_layers = set(range(lo, hi+1))
        low = min(layers[i]['centre_z_m']-layers[i]['thickness_m']/2 for i in pad_layers)
        high = max(layers[i]['centre_z_m']+layers[i]['thickness_m']/2 for i in pad_layers)
        record['intervals'].append(dict(low=low,high=high,layers=pad_layers));record['layers'].update(pad_layers);record['nets'].add(via['net'])
    for record in records.values():
        spans = []
        for interval in sorted(record['intervals'],key=lambda value:value['low']):
            if not spans or interval['low'] > spans[-1]['high']:
                spans.append(dict(low=interval['low'],high=interval['high'],layers=set(interval['layers'])))
            else:
                spans[-1]['high']=max(spans[-1]['high'],interval['high']);spans[-1]['layers'].update(interval['layers'])
        record.update(spans=spans,low=spans[0]['low'],high=spans[-1]['high'])
    return records


def build(snapshot):
    from netgen.occ import Pnt, Dir, Cylinder
    if snapshot['schema'] != 'finite-dc-winding-circular-qualification-v1' or snapshot['routing'].get('splines'):
        raise ValueError('Actual circular-qualification snapshot without splines required')
    if any(snapshot['routing'].get(key) for key in ['io_pads', 'io_traces']):
        raise ValueError('IO copper has no qualified finite-solid interpretation')
    spec = dimensions(snapshot);layers = spec['layers'];pieces = []
    for segment in snapshot['routing']['segments']:
        layer = layers[segment['layer']]
        xy = [[segment[key]['x']*1e-3, segment[key]['y']*1e-3] for key in ['start', 'end']]
        points = np.column_stack([xy, [layer['centre_z_m']]*2])
        pieces.append(trace_solid(points, layer['trace_width_m'], layer['thickness_m']))
    for curve in snapshot['routing']['curves']:
        layer = layers[curve['layer']]
        primitive = {key:[curve[key]['x']*1e-3, curve[key]['y']*1e-3] for key in ['start', 'mid', 'end']}
        pieces.append(arc_solid(primitive, layer['centre_z_m'], layer['trace_width_m'], layer['thickness_m']))
    vias = via_records(snapshot)
    for (x, y), via in vias.items():
        for span in via['spans']:
            low, high = span['low'], span['high']
            pieces.append(Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_outer_radius_m'],high-low)
                          -Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_inner_radius_m'],high-low))
        for index in sorted(via['layers']):
            layer = layers[index];low = layer['centre_z_m']-layer['thickness_m']/2
            pieces.append(Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_pad_radius_m'],layer['thickness_m']))
    copper = fuse_all(pieces)
    holes = []
    for (x,y),via in vias.items():
        for span in via['spans']:
            holes.append(Cylinder(Pnt(x,y,span['low']),Dir(0,0,1),spec['via_inner_radius_m'],span['high']-span['low']))
    # Exact CSG identity C\(H1 union ... Hn), not repeated whole-CAD cuts.
    # Never span a physical blind-via gap merely to build a cheaper cutter.
    if holes:copper = copper-fuse_all(holes)
    copper.mat('copper');copper.faces.name='copper_surface'
    graph_extents = {}
    for network in snapshot['networks']:
        for edge in network['edges']:
            geometry = edge['geometry']
            if geometry['kind'] == 'via':
                graph_extents.setdefault(tuple(geometry['position_m']), []).extend(
                    layer_z(snapshot['sim'], snapshot['geometry_hints'], layer) for layer in geometry['layers'])
    stubs = []
    for xy,via in vias.items():
        graph = graph_extents.get(xy, [])
        raw = [layers[i]['centre_z_m'] for i in via['layers']]
        if not graph or min(raw) != min(graph) or max(raw) != max(graph):
            stubs.append(dict(position_m=list(xy), full_centreplane_range_m=[min(raw),max(raw)],
                              electrical_landing_range_m=[min(graph),max(graph)] if graph else None))
    return copper, dict(spec, trace_edges=len(snapshot['routing']['segments'])+len(snapshot['routing']['curves']),
        circular_arc_edges=len(snapshot['routing']['curves']), distinct_via_positions=len(vias),
        physical_via_spans=sum(len(via['spans']) for via in vias.values()),
        gapped_via_positions=sum(len(via['spans'])>1 for via in vias.values()),
        volume_m3=float(copper.mass), solid_components=len(copper.solids), full_physical_via_stubs=stubs,
        physical_via_semantics='Full declared from/to barrel and annular pads at saved copper planes in that span; graph landing length never truncates a physical via.')


def validate_snapshot(snapshot):
    controls = []
    for network in snapshot['networks']:
        resistance = resistances(network, snapshot['sim'], snapshot['drive'], snapshot['geometry_hints'])
        shares, equivalent = unit_currents(network, resistance)
        if (not np.allclose(resistance, [edge['r_ohm'] for edge in network['edges']], rtol=1e-12, atol=1e-15)
            or not np.allclose(shares, network['rust_current_share'], rtol=0., atol=1e-9)
            or not np.isclose(equivalent, network['rust_resistance_ohm'], rtol=1e-9, atol=1e-12)):
            raise ValueError('Independent electrical graph resistance/current/power balance failed')
        for edge in network['edges']:
            geometry = edge['geometry']
            if 'circular_arc_m' in geometry:
                control = chord_control(geometry);control['net'] = network['net'];controls.append(control)
                if not control['passed']:raise ValueError('Circular graph length fails unchanged 2% geometry control')
    if len(controls) != len(snapshot['routing']['curves']):
        raise ValueError('Circular primitive coverage differs from physical CAD')
    return controls


def validate_geometry_reuse(prior, inputs, snapshot):
    if prior.get('status') != 'failed' or prior.get('error') != "'str' object has no attribute 'read_bytes'":
        raise ValueError('Only the preserved post-CAD input-path validation failure may supply a geometry checkpoint')
    if prior['input_hashes'] != inputs:
        raise ValueError('Reused imported CAD has different immutable physical inputs')
    expected = {'finite_circular_copper.py','finite_copper_geometry.py','closed_winding.py','winding_oracle.py','source_snapshot.py'}
    if not expected.issubset({Path(path).name for path in prior.get('source_snapshots',{})}):
        raise ValueError('Reused imported CAD lacks construction implementation provenance')
    for key, value in dimensions(snapshot).items():
        if prior['geometry'][key] != value:
            raise ValueError('Reused imported CAD changed saved copper dimensions')
    # Only the final report's Path conversion was repaired. Every actual CAD/
    # source-construction dependency must remain byte-identical to that trial.
    for path,entry in prior['source_snapshots'].items():
        if Path(path).name != Path(__file__).name and sha(Path(path)) != entry['sha256']:
            raise ValueError('Reused imported CAD construction implementation changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-log', type=Path, required=True);parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--geometry-work',type=Path,help='Reuse only verified CAD from the preserved post-CAD report-path failure; never a current solution')
    add_thread_option(parser);args = parser.parse_args()
    work = args.work.resolve()
    if work.exists():parser.error('Fresh geometry directory required')
    log = args.export_log.resolve();receipt_path = Path(str(log)+'.command.json')
    completed_receipt({'command_receipt':str(receipt_path)})
    metadata = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{"')]
    if len(metadata) != 1 or metadata[0].get('qualification_only') is not True or metadata[0].get('imported') is not True:
        raise ValueError('Successful actual-import qualification export required')
    metadata = metadata[0];snapshot_path = Path(metadata['snapshot']);project = Path(metadata['source_project'])
    if sha(snapshot_path) != metadata['snapshot_sha256'] or sha(project) != metadata['source_sha256']:
        raise ValueError('Actual snapshot/project changed after production export')
    declaration_path = args.declaration.resolve();declaration = json.loads(declaration_path.read_text())
    if (declaration['schema'] != 'finite-dc-source-only-study-v1' or declaration['snapshot_sha256'] != sha(snapshot_path)
        or declaration['source_project_sha256'] != sha(project) or declaration['version_index'] != metadata['version_index']
        or declaration['material_coupling'] is not False):
        raise ValueError('Explicit source-only study must match actual immutable project/version/snapshot')
    snapshot = json.loads(snapshot_path.read_text());controls = validate_snapshot(snapshot)
    shift = np.array([0.,0.,0.])
    _,_,closure = closed_graph(snapshot, declaration['positive_phase'], declaration['negative_phase'], shift,
                              declaration['external_return_waypoints_m'])
    inputs = {str(path):sha(path) for path in [snapshot_path,project,log,receipt_path,declaration_path]}
    work.mkdir(parents=True);started=time.monotonic()
    snapshots = capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
        ['finite_circular_copper.py','finite_copper_geometry.py','closed_winding.py','winding_oracle.py']]])
    report = dict(status='running',scope=__doc__,input_hashes=inputs,translation_m=shift.tolist(),
        source_snapshots=snapshots,execution=runtime_metadata(),circular_graph_controls=controls,failures=[])
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        if args.geometry_work:
            from netgen.occ import OCCGeometry
            prior_work = args.geometry_work.resolve();prior_path = prior_work/'summary.json'
            prior = json.loads(prior_path.read_text());validate_geometry_reuse(prior,inputs,snapshot)
            receipt = json.loads(Path(prior['command_receipt']).read_text())
            if receipt.get('status') != 'failed' or receipt.get('exit_code') != 1:
                raise ValueError('Reused imported CAD checkpoint has no completed failed receipt')
            if sha(prior_work/'copper.brep') != prior['brep_sha256']:
                raise ValueError('Imported CAD checkpoint bytes changed')
            shutil.copy2(prior_work/'copper.brep',work/'copper.brep')
            if sha(work/'copper.brep') != prior['brep_sha256']:
                raise ValueError('Imported CAD checkpoint changed while copied')
            copper=OCCGeometry(str(work/'copper.brep')).shape;spec=prior['geometry']
            if abs(float(copper.mass)/spec['volume_m3']-1)>1e-9 or len(copper.solids)!=spec['solid_components']:
                raise ValueError('Exact imported CAD checkpoint reload failed')
            report['geometry_input_reuse']=dict(work=str(prior_work),summary_sha256=sha(prior_path),
                source_status=prior['status'],scope='Geometry bytes only from post-CAD validation failure. Physical inputs/dependencies/reload verified anew; no solution, force or failed acceptance imported.')
        else:
            copper,spec=build(snapshot);copper.WriteBrep(str(work/'copper.brep'))
        report.update(geometry=spec,brep_sha256=sha(work/'copper.brep'))
        # Separate named return input carries no magnetic solve status. It is a
        # declared screening path, not recovered cable CAD or a physical repair.
        return_work = work/'return';return_work.mkdir()
        returned = dict(status='prepared-physical-dc-return-geometry-only',closure=closure,translation_m=shift.tolist(),
            input_hashes=inputs,source_snapshots=capture(return_work,[Path(__file__),Path(__file__).with_name('closed_winding.py')]),
            failures=[],command_receipt=report.get('command_receipt'),
            scope='Explicit source-only return, graph closure/current/power checked. No magnetic model, solve or qualification.')
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Actual imported geometry input changed')
        for path,entry in snapshots.items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Imported geometry implementation changed')
        (return_work/'summary.json').write_text(json.dumps(returned,indent=2,allow_nan=False)+'\n')
        report.update(status='completed-finite-copper-geometry-only-unqualified',seconds=time.monotonic()-started)
        save();print(report['status'],report['seconds'],flush=True)
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__ == '__main__':threaded_main(main)
