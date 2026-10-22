#!/usr/bin/env python3
"""Exact finite copper fused by primitive kind instead of one pairwise tree.

Builds the identical trace, barrel and pad solids as finite_copper_geometry.build
and applies the identical drill bores. Only the Boolean grouping differs: all
traces, all barrels and each pad layer are fused separately, then together.
That order changes no dimension, position or connection. A declared analytic
union audit must still accept the result; nothing is healed or substituted.
"""
import numpy as np

from audit_copper_union_volume import primitives
from finite_copper_geometry import dimensions,edge_points,fuse_all,layer_z,trace_solid


def build_groups(fixture,shift):
    """Build pieces in finite_copper_geometry.build order with their analytic primitives."""
    from netgen.occ import Pnt,Dir,Cylinder
    analytic,_=primitives(fixture,shift);spec=dimensions(fixture);layers={x['layer']:x for x in spec['layers']}
    shift=np.asarray(shift,dtype=float);pieces=[];groups=[];cursor=0;bores={}
    for network in fixture['networks']:
        for index,edge in enumerate(network['edges']):
            geometry=edge['geometry'];points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            if geometry['kind']!='trace':
                pair=geometry['layers']
                low=min(layer_z(fixture['sim'],fixture['geometry_hints'],l)-layers[l]['thickness_m']/2 for l in pair)+shift[2]
                high=max(layer_z(fixture['sim'],fixture['geometry_hints'],l)+layers[l]['thickness_m']/2 for l in pair)+shift[2]
                entry=bores.setdefault(tuple(points[0,:2]),dict(low=low,high=high,layers=set()))
                entry['low']=min(entry['low'],low);entry['high']=max(entry['high'],high);entry['layers'].update(pair);continue
            layer=layers[geometry['layer']];pieces.append(trace_solid(points,layer['trace_width_m'],layer['thickness_m']))
            size=2*len(points)-1;groups.append(dict(label=f"trace:{network['net']}:{index}",primitives=list(range(cursor,cursor+size))));cursor+=size
    for (x,y),via in bores.items():
        low,high=via['low'],via['high']
        pieces.append(Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_outer_radius_m'],high-low)-Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_inner_radius_m'],high-low))
        groups.append(dict(label=f'barrel:{x:.6g}:{y:.6g}',primitives=[cursor]));cursor+=1
        for layer_index in sorted(via['layers']):
            layer=layers[layer_index];z=layer['centre_z_m']+shift[2]-layer['thickness_m']/2
            pieces.append(Cylinder(Pnt(x,y,z),Dir(0,0,1),spec['via_pad_radius_m'],layer['thickness_m'])-Cylinder(Pnt(x,y,z),Dir(0,0,1),spec['via_inner_radius_m'],layer['thickness_m']))
            groups.append(dict(label=f'pad:{x:.6g}:{y:.6g}:{layer_index}',primitives=[cursor]));cursor+=1
    if cursor!=len(analytic):raise ValueError('Build replay and analytic primitive inventory differ')
    return pieces,groups,analytic


def kind(label):
    if label.startswith('pad:'):return 'pad:'+label.split(':')[-1]
    return label.split(':')[0]


def grouped_build(fixture,shift):
    """Same pieces/drills/metadata as build(), fused by primitive kind."""
    from netgen.occ import Pnt,Dir,Cylinder
    from finite_copper_eligibility import require_network_representable
    spec=dimensions(fixture);require_network_representable(fixture,spec)
    shift=np.asarray(shift,dtype=float)
    if shift.shape!=(3,) or not np.isfinite(shift).all():raise ValueError('Invalid rigid copper translation')
    pieces,groups,_=build_groups(fixture,shift)
    names=sorted({kind(g['label']) for g in groups})
    parts={name:fuse_all([p for p,g in zip(pieces,groups) if kind(g['label'])==name]) for name in names}
    bores=[g for g in groups if g['label'].startswith('barrel:')]
    _,drills=primitives(fixture,shift)
    if drills:
        # (A-D)+(B-D) equals (A+B)-D for any parts, so cutting each kind once
        # with the fused bores replaces hundreds of cuts on the whole union.
        bore=fuse_all([Cylinder(Pnt(d['centre'][0],d['centre'][1],d['z'][0]),Dir(0,0,1),spec['via_inner_radius_m'],d['z'][1]-d['z'][0]) for d in drills])
        parts={name:part-bore for name,part in parts.items()}
    copper=fuse_all([parts[name] for name in names])
    copper.mat('copper');copper.faces.name='copper_surface'
    traces=sum(1 for g in groups if g['label'].startswith('trace:'))
    return copper,dict(spec,trace_edges=traces,distinct_via_positions=len(bores),solid_components=len(copper.solids),
        volume_m3=float(copper.mass),fuse_strategy='per-kind',fuse_groups=names)
