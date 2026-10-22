#!/usr/bin/env python3
"""Find the first pairwise fuse that silently loses declared copper volume.

Diagnostic only. Replays the unchanged build pieces and compares each OCC fuse
node with the analytic union of the declared primitives it covers. No CAD from
this replay is used downstream and nothing is repaired.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from audit_copper_union_volume import primitives,union_estimate
from finite_copper_geometry import dimensions,edge_points,layer_z,trace_solid

LOSS_GATE=.005


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


def lossy(pieces,expected,left,right):
    from finite_copper_geometry import fuse_all
    a=fuse_all([pieces[i] for i in left]);b=fuse_all([pieces[i] for i in right])
    va,ea=expected(left);vb,eb=expected(right);vc,ec=expected(left+right)
    def bad(x,v,e):return abs(float(x.mass)/v-1)>max(LOSS_GATE,4*e/v)
    return (not bad(a,va,ea)) and (not bad(b,vb,eb)) and bad(a+b,vc,ec)


def shrink(pieces,groups,expected,left,right):
    """Halve each side while a faithful-left plus faithful-right fuse still loses volume."""
    steps=0
    for side in ['right','left','right','left']:
        while True:
            current=right if side=='right' else left
            if len(current)==1:break
            half=len(current)//2;found=None
            for part in [current[:half],current[half:]]:
                steps+=1
                if (lossy(pieces,expected,left,part) if side=='right' else lossy(pieces,expected,part,right)):found=part;break
            if found is None:break
            if side=='right':right=found
            else:left=found
    return dict(steps=steps,left=[groups[i]['label'] for i in left],right=[groups[i]['label'] for i in right],
        left_indices=left,right_indices=right,still_lossy=bool(lossy(pieces,expected,left,right)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-work',type=Path,required=True);parser.add_argument('--copper-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--samples',type=int,default=1500)
    parser.add_argument('--shrink',action='store_true',help='greedily shrink the first lossy fuse to a small reproducer');args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous diagnostics')
    fixture=json.loads((args.study_work.resolve()/'fixture.json').read_text())
    shift=json.loads((args.copper_work.resolve()/'summary.json').read_text())['translation_m']
    pieces,groups,analytic=build_groups(fixture,shift)
    def expected(indices):
        value,error=union_estimate([analytic[i] for g in indices for i in groups[g]['primitives']],[],args.samples);return value,error
    report=dict(scope=__doc__,pieces=len(pieces),primitives=len(analytic),loss_gate=LOSS_GATE,lossy_pieces=[],first_lossy_fuse=None,levels=[])
    for g,piece in enumerate(pieces):
        value,error=expected([g]);actual=float(piece.mass)
        if abs(actual/value-1)>max(LOSS_GATE,4*error/value):report['lossy_pieces'].append(dict(groups[g],occ_m3=actual,analytic_m3=value))
    nodes=[(piece,[g]) for g,piece in enumerate(pieces)];level=0
    while len(nodes)>1 and report['first_lossy_fuse'] is None:
        merged=[];checked=0
        for k in range(0,len(nodes),2):
            if k+1==len(nodes):merged.append(nodes[k]);continue
            (a,ia),(b,ib)=nodes[k],nodes[k+1];c=a+b;actual=float(c.mass);value,error=expected(ia+ib);checked+=1
            if abs(actual/value-1)>max(LOSS_GATE,4*error/value):
                if args.shrink:report['reproducer']=shrink(pieces,groups,expected,ia,ib)
                report['first_lossy_fuse']=dict(level=level,occ_m3=actual,analytic_m3=value,standard_error_m3=error,
                    left_occ_m3=float(a.mass),right_occ_m3=float(b.mass),left=[groups[i]['label'] for i in ia],right=[groups[i]['label'] for i in ib])
                break
            merged.append((c,ia+ib))
        report['levels'].append(dict(level=level,checked=checked));nodes=merged;level+=1
        print('level',level-1,'checked',checked,'lossy' if report['first_lossy_fuse'] else 'ok',flush=True)
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2,default=float)+'\n')
    print(json.dumps(dict(lossy_pieces=report['lossy_pieces'][:10],first=report['first_lossy_fuse'],reproducer=report.get('reproducer')),default=float)[:6000])


if __name__=='__main__':main()
