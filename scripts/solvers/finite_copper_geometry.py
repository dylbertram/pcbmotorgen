#!/usr/bin/env python3
"""Finite trace/pad/barrel geometry from the saved winding export settings.

Uses the legacy exported depth planes as centreplanes, recording actual finite
extents rather than inventing a source radius. This is geometry preparation,
not a current-distribution or electromagnetic qualification. Magnetic-region
overlap is measured and retained, never silently resolved by adding a gap.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture
from winding_oracle import edge_points,layer_z
from winding_coordinates import translation


def dimensions(fixture):
    sim=fixture['sim'];drive=fixture['drive'];hints=fixture['geometry_hints'];layers=[]
    for layer in range(sim['num_layers']):
        inner=sim['num_layers']>2 and layer not in [0,sim['num_layers']-1]
        weight=drive['inner_copper_oz'] if inner else drive['outer_copper_oz'];thickness=weight*35e-6
        layers.append({'layer':layer,'centre_z_m':layer_z(sim,hints,layer),'copper_oz':weight,'thickness_m':thickness,'trace_width_m':sim['min_trace_m']})
    drill=sim['min_via_drill_m'];plating=drive['via_plating_m'];ring=sim['min_via_annular_ring_m']
    values=[drill,plating,ring,*[x[k] for x in layers for k in ['thickness_m','trace_width_m']]]
    if not np.isfinite(values).all() or min(values)<=0 or not layers:raise ValueError('Invalid saved finite copper dimensions')
    if drill/2+ring<drill/2+plating:raise ValueError('Saved via pad does not contain plated barrel')
    rho=1.724e-8*(1+.00393*(drive['winding_temp_c']-20.))
    if not np.isfinite(rho) or rho<=0:raise ValueError('Invalid saved winding temperature')
    return {'layers':layers,'via_inner_radius_m':drill/2,'via_outer_radius_m':drill/2+plating,'via_pad_radius_m':drill/2+ring,
        'via_plating_m':plating,'via_barrel_area_m2':np.pi*plating*(drill+plating),'copper_resistivity_ohm_m':rho,
        'temperature_c':drive['winding_temp_c'],'depth_convention':'exported centreplanes preserved; finite copper extends by half its saved thickness each side'}


def fuse_all(shapes):
    if not shapes:raise ValueError('No finite copper solids')
    shapes=list(shapes)
    while len(shapes)>1:shapes=[shapes[i]+shapes[i+1] if i+1<len(shapes) else shapes[i] for i in range(0,len(shapes),2)]
    return shapes[0]


def trace_solid(points,width,thickness):
    from netgen.occ import Pnt,Vec,Dir,Segment,Wire,Face,Cylinder
    points=np.asarray(points,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.isfinite(points).all() or min(width,thickness)<=0:
        raise ValueError('Invalid finite trace')
    if not np.all(points[:,2]==points[0,2]):raise ValueError('Trace must remain in its saved layer plane')
    z=points[0,2]-thickness/2;pieces=[]
    for a,b in zip(points[:-1],points[1:]):
        vector=b[:2]-a[:2];length=np.linalg.norm(vector)
        if length<=0:raise ValueError('Zero-length copper trace segment')
        normal=np.array([-vector[1],vector[0]])/length*width/2
        corners=[np.r_[p,z] for p in [a[:2]+normal,b[:2]+normal,b[:2]-normal,a[:2]-normal]]
        face=Face(Wire([Segment(Pnt(*corners[i]),Pnt(*corners[(i+1)%4])) for i in range(4)]))
        pieces.append(face.Extrude(Vec(0,0,thickness)))
    for point in points:pieces.append(Cylinder(Pnt(point[0],point[1],z),Dir(0,0,1),width/2,thickness))
    return fuse_all(pieces)


def build(fixture,shift):
    from netgen.occ import Pnt,Dir,Cylinder
    spec=dimensions(fixture);shift=np.asarray(shift,dtype=float)
    from finite_copper_eligibility import require_network_representable
    require_network_representable(fixture,spec)
    if shift.shape!=(3,) or not np.isfinite(shift).all():raise ValueError('Invalid rigid copper translation')
    layers={x['layer']:x for x in spec['layers']};pieces=[];via_intervals={};trace_count=0
    for network in fixture['networks']:
        for edge in network['edges']:
            geometry=edge['geometry'];points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            if geometry['kind']=='trace':
                layer=layers[geometry['layer']];pieces.append(trace_solid(points,layer['trace_width_m'],layer['thickness_m']));trace_count+=1
            elif geometry['kind']=='via':
                pair=geometry['layers'];low=min(layer_z(fixture['sim'],fixture['geometry_hints'],l)-layers[l]['thickness_m']/2 for l in pair)+shift[2]
                high=max(layer_z(fixture['sim'],fixture['geometry_hints'],l)+layers[l]['thickness_m']/2 for l in pair)+shift[2]
                key=tuple(points[0,:2]);entry=via_intervals.setdefault(key,{'low':low,'high':high,'layers':set()})
                entry['low']=min(entry['low'],low);entry['high']=max(entry['high'],high);entry['layers'].update(pair)
            else:raise ValueError('Unsupported exported copper edge')
    for (x,y),via in via_intervals.items():
        low,high=via['low'],via['high'];outer=Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_outer_radius_m'],high-low)
        inner=Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_inner_radius_m'],high-low);pieces.append(outer-inner)
        for index in sorted(via['layers']):
            layer=layers[index];z=layer['centre_z_m']+shift[2]-layer['thickness_m']/2
            pad=Cylinder(Pnt(x,y,z),Dir(0,0,1),spec['via_pad_radius_m'],layer['thickness_m'])
            hole=Cylinder(Pnt(x,y,z),Dir(0,0,1),spec['via_inner_radius_m'],layer['thickness_m']);pieces.append(pad-hole)
    copper=fuse_all(pieces)
    # Drill holes apply to the whole union, including trace copper underneath
    # pads, so no current-bearing solid is inadvertently left in a via bore.
    for (x,y),via in via_intervals.items():
        copper=copper-Cylinder(Pnt(x,y,via['low']),Dir(0,0,1),spec['via_inner_radius_m'],via['high']-via['low'])
    copper.mat('copper');copper.faces.name='copper_surface'
    return copper,dict(spec,trace_edges=trace_count,distinct_via_positions=len(via_intervals),solid_components=len(copper.solids),volume_m3=float(copper.mass))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copper-work',type=Path,required=True);parser.add_argument('--model-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    add_thread_option(parser);args=parser.parse_args();copper_work=args.copper_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous finite copper geometries')
    exported=json.loads((copper_work/'summary.json').read_text());completed_receipt(exported)
    if exported['status']!='passed-original-version-copper-export-only' or exported['failures']:raise ValueError('Unaccepted saved copper export')
    audit_path=copper_work/'free-space-copper-audit/summary.json';audit=json.loads(audit_path.read_text())
    if sha(audit_path)!=exported['copper_audit_sha256']:raise ValueError('Copper audit changed')
    level=max(audit['levels'],key=int);fixture_path=copper_work/f'free-space-copper-audit/mesh-{level}/fixture.json'
    if sha(fixture_path)!=audit['levels'][level]['fixture_sha256']:raise ValueError('Copper fixture changed')
    model_path=args.model_work/'summary.json';source=json.loads(model_path.read_text());model=source['model']
    completed_receipt(source)
    if source.get('failures')!=[]:raise ValueError('Unaccepted physical-model source')
    if model['source_sha256']!=exported['source_project_sha256'] or model['version_index']!=exported['version_index']:raise ValueError('Different saved project/version')
    fixture=json.loads(fixture_path.read_text());shift=translation(fixture['sim'],model,exported['saved_mover_position_mm']*1e-3)
    work.mkdir(parents=True);started=time.monotonic();report={'status':'running','scope':__doc__,'execution':runtime_metadata(),
        'source_snapshots':capture(work,[Path(__file__),Path(__file__).with_name('winding_oracle.py'),Path(__file__).with_name('winding_coordinates.py'),Path(__file__).with_name('finite_copper_eligibility.py')]),
        'input_hashes':{str(p):sha(p) for p in [copper_work/'summary.json',fixture_path,model_path]},'translation_m':shift.tolist()}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        shape,spec=build(fixture,shift);shape.WriteBrep(str(work/'copper.brep'));report['geometry']=spec;report['brep_sha256']=sha(work/'copper.brep')
        from netgen.occ import Box,Pnt
        overlap={}
        for layer in model['stack']:
            if layer['mu_r']<=1:continue
            low=np.array(layer['origin_m']);high=low+layer['size_m'];intersection=shape*Box(Pnt(*low),Pnt(*high))
            overlap[layer['name']]=float(intersection.mass)
        report['nominal_magnetic_overlap_m3']=overlap
        for p,digest in report['input_hashes'].items():
            if sha(Path(p))!=digest:raise ValueError('Finite copper input changed')
        for p,entry in report['source_snapshots'].items():
            if sha(Path(p))!=entry['sha256']:raise ValueError('Finite copper implementation changed')
        report.update(status='completed-finite-copper-geometry-only-unqualified',seconds=time.monotonic()-started,
            remaining=['connectivity/clearance and mesh controls','DC current distribution/return closure','non-overlapping magnetic-region construction','finite-source field/self-inductance qualification']);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
