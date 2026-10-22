#!/usr/bin/env python3
"""Find sufficient geometric witnesses of undeclared cross-phase pad shorts.

Uses actual saved pad radii, layer extents and global drill bores. A positive
radius ball inside two different phases' non-star pads and outside every bore
proves a physical contact omitted from the separate phase graphs. No contact
is repaired. Absence of these midpoint witnesses is NOT a clearance audit or
proof of representable topology. Native arcs and other contact types need their
own checks. Optional mesh verification locates the witnesses in actual copper.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from finite_copper_geometry import dimensions
from post_project_force import sha
from source_snapshot import capture
from winding_oracle import edge_points


def cylinder_clearance(point,centre,radius,low,high):
    radial=float(np.linalg.norm(point[:2]-centre))-radius
    vertical=max(low-point[2],point[2]-high,0.)
    return float(np.hypot(max(radial,0.),vertical)) if vertical else radial


def witnesses(fixture,shift):
    spec=dimensions(fixture);shift=np.asarray(shift,dtype=float)
    if shift.shape!=(3,) or not np.isfinite(shift).all():raise ValueError('Finite saved translation required')
    layers={layer['layer']:layer for layer in spec['layers']};vias=[];bores={}
    for network in fixture['networks']:
        for index,edge in enumerate(network['edges']):
            if edge['geometry']['kind']!='via':continue
            pair=edge['geometry']['layers'];point=(edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift)[0,:2]
            low=min(layers[i]['centre_z_m']-layers[i]['thickness_m']/2 for i in pair)+shift[2]
            high=max(layers[i]['centre_z_m']+layers[i]['thickness_m']/2 for i in pair)+shift[2]
            prior=bores.setdefault(tuple(point),[low,high]);prior[0]=min(prior[0],low);prior[1]=max(prior[1],high)
            vias.append(dict(net=network['net'],edge=index,point=point,layers=set(pair),
                star_incident=bool({edge['a'],edge['b']}&set(network['star']))))
    found=[];inner=spec['via_inner_radius_m'];outer=spec['via_pad_radius_m']
    for i,first in enumerate(vias):
        for second in vias[i+1:]:
            if first['net']==second['net'] or first['star_incident'] or second['star_incident']:continue
            midpoint=(first['point']+second['point'])/2
            radial=[float(np.linalg.norm(midpoint-v['point'])) for v in [first,second]]
            if not all(inner<value<outer for value in radial):continue
            for layer_index in sorted(first['layers']&second['layers']):
                layer=layers[layer_index];point=np.r_[midpoint,layer['centre_z_m']+shift[2]]
                clearances=[layer['thickness_m']/2,*[outer-value for value in radial],*[value-inner for value in radial]]
                clearances.extend(cylinder_clearance(point,np.asarray(centre),inner,*interval) for centre,interval in bores.items())
                radius=min(clearances)/2
                if radius<=0:continue
                found.append(dict(first=dict(net=first['net'],edge=first['edge'],centre_xy_m=first['point'].tolist()),
                    second=dict(net=second['net'],edge=second['edge'],centre_xy_m=second['point'].tolist()),layer=layer_index,
                    centre_spacing_m=float(np.linalg.norm(first['point']-second['point'])),pad_radius_m=outer,
                    drill_radius_m=inner,point_m=point.tolist(),positive_contact_ball_radius_m=float(radius)))
    return found


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copper-work',type=Path,required=True)
    parser.add_argument('--mesh-work',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous contact diagnostics')
    work=args.copper_work.resolve();summary=work/'summary.json';geometry=json.loads(summary.read_text())
    fixtures=[Path(p) for p in geometry['input_hashes'] if p.endswith('/fixture.json')]
    if len(fixtures)!=1 or sha(fixtures[0])!=geometry['input_hashes'][str(fixtures[0])]:raise ValueError('Unique unchanged actual fixture required')
    fixture=fixtures[0];inputs={str(p):sha(p) for p in [summary,fixture,work/'copper.brep']}
    if inputs[str(work/'copper.brep')]!=geometry['brep_sha256']:raise ValueError('Saved physical copper changed')
    found=witnesses(json.loads(fixture.read_text()),geometry['translation_m'])
    if args.mesh_work:
        import ngsolve as ng
        source=args.mesh_work.resolve();source_report=json.loads((source/'summary.json').read_text())
        if source_report['input_hashes'].get(str(summary))!=sha(summary):raise ValueError('Mesh belongs to different physical copper')
        if sha(source/'mesh.vol')!=source_report['mesh_sha256']:raise ValueError('Source mesh changed')
        for path in [source/'summary.json',source/'mesh.vol']:inputs[str(path)]=sha(path)
        mesh=ng.Mesh(str(source/'mesh.vol'))
        if found:
            points=np.asarray([item['point_m'] for item in found]);located=mesh(points[:,0],points[:,1],points[:,2])
            for item,element in zip(found,located['nr']):item['inside_actual_copper_mesh']=bool(element>=0)
    report=dict(status='proved-undeclared-cross-phase-pad-contacts' if found else 'no-midpoint-pad-contact-witness-not-qualified',
        scope=__doc__,input_hashes=inputs,contact_witnesses=found,
        distinct_edge_pairs=len({(v['first']['net'],v['first']['edge'],v['second']['net'],v['second']['edge']) for v in found}),
        physical_inputs_changed=False,qualification=False,
        source_snapshots=capture(args.output.parent,[Path(__file__),Path(__file__).with_name('finite_copper_geometry.py'),Path(__file__).with_name('winding_oracle.py')]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Contact diagnostic input changed')
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(report['status'],'pairs',report['distinct_edge_pairs'],'layer witnesses',len(found),flush=True)


if __name__=='__main__':main()
