#!/usr/bin/env python3
"""Locate the first empty Boolean step in an actual prepared copper build.

Diagnostic only: replays the unchanged construction from the saved study
fixture and records where a nonempty fuse or drill result loses its volume.
Writes no CAD for downstream use and performs no repair.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from finite_copper_geometry import dimensions,edge_points,layer_z,trace_solid


def mass(shape):
    try:return float(shape.mass),len(shape.solids)
    except Exception as error:return None,str(error)


def tree(pieces):
    from finite_copper_geometry import fuse_all
    return fuse_all(list(pieces))


def bisect(pieces,labels,failure):
    """Greedy shrink of each side while the two-sided fuse stays empty."""
    left=[item['index'] for item in failure['left_pieces']];right=[item['index'] for item in failure['right_pieces']]
    left=list(range(left[0],left[0]+failure['left_count']));right=list(range(right[0],right[0]+failure['right_count']))
    def empty(a,b):
        x,y=tree([pieces[i] for i in a]),tree([pieces[i] for i in b]);vx,_=mass(x);vy,_=mass(y);vz,_=mass(x+y)
        return bool(vx and vy and not vz)
    steps=0
    for side in ['right','left']:
        while True:
            current=right if side=='right' else left
            if len(current)==1:break
            half=len(current)//2;shrunk=None
            for part in [current[:half],current[half:]]:
                steps+=1
                if (empty(left,part) if side=='right' else empty(part,right)):shrunk=part;break
            if shrunk is None:break
            if side=='right':right=shrunk
            else:left=shrunk
    return dict(steps=steps,left=[labels[i]|dict(index=i) for i in left][:64],right=[labels[i]|dict(index=i) for i in right][:64],
        left_count=len(left),right_count=len(right),still_empty=empty(left,right))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-work',type=Path,required=True);parser.add_argument('--copper-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--bisect',action='store_true',help='shrink the failing fuse to a small failing piece set');args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous diagnostics')
    from netgen.occ import Pnt,Dir,Cylinder
    fixture=json.loads((args.study_work.resolve()/'fixture.json').read_text())
    shift=np.asarray(json.loads((args.copper_work.resolve()/'summary.json').read_text())['translation_m'],dtype=float)
    spec=dimensions(fixture);layers={x['layer']:x for x in spec['layers']};pieces=[];labels=[];via_intervals={}
    for network in fixture['networks']:
        for edge in network['edges']:
            geometry=edge['geometry'];points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            if geometry['kind']=='trace':
                layer=layers[geometry['layer']];pieces.append(trace_solid(points,layer['trace_width_m'],layer['thickness_m']))
                labels.append(dict(kind='trace',network=network.get('name'),layer=geometry['layer'],points=len(points)))
            else:
                pair=geometry['layers'];low=min(layer_z(fixture['sim'],fixture['geometry_hints'],l)-layers[l]['thickness_m']/2 for l in pair)+shift[2]
                high=max(layer_z(fixture['sim'],fixture['geometry_hints'],l)+layers[l]['thickness_m']/2 for l in pair)+shift[2]
                entry=via_intervals.setdefault(tuple(points[0,:2]),{'low':low,'high':high,'layers':set()})
                entry['low']=min(entry['low'],low);entry['high']=max(entry['high'],high);entry['layers'].update(pair)
    for (x,y),via in via_intervals.items():
        low,high=via['low'],via['high']
        pieces.append(Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_outer_radius_m'],high-low)-Cylinder(Pnt(x,y,low),Dir(0,0,1),spec['via_inner_radius_m'],high-low))
        labels.append(dict(kind='barrel',xy=[x,y]))
        for index in sorted(via['layers']):
            layer=layers[index];z=layer['centre_z_m']+shift[2]-layer['thickness_m']/2
            pieces.append(Cylinder(Pnt(x,y,z),Dir(0,0,1),spec['via_pad_radius_m'],layer['thickness_m'])-Cylinder(Pnt(x,y,z),Dir(0,0,1),spec['via_inner_radius_m'],layer['thickness_m']))
            labels.append(dict(kind='pad',xy=[x,y],layer=index))
    report=dict(scope=__doc__,pieces=len(pieces),empty_pieces=[],first_empty_fuse=None,fuse_levels=[])
    for i,piece in enumerate(pieces):
        volume,_=mass(piece)
        if not volume:report['empty_pieces'].append(dict(index=i,**labels[i]))
    shapes=[(p,[i]) for i,p in enumerate(pieces)];level=0
    while len(shapes)>1 and report['first_empty_fuse'] is None:
        merged=[]
        for k in range(0,len(shapes),2):
            if k+1==len(shapes):merged.append(shapes[k]);continue
            (a,ia),(b,ib)=shapes[k],shapes[k+1];c=a+b;va,_=mass(a);vb,_=mass(b);vc,info=mass(c)
            if va and vb and not vc:
                report['first_empty_fuse']=dict(level=level,left_volume_m3=va,right_volume_m3=vb,result=[vc,info],
                    left_pieces=[labels[i]|dict(index=i) for i in ia][:40],right_pieces=[labels[i]|dict(index=i) for i in ib][:40],
                    left_count=len(ia),right_count=len(ib));break
            merged.append((c,ia+ib))
        report['fuse_levels'].append(dict(level=level,shapes=len(merged)));shapes=merged;level+=1
    if report['first_empty_fuse'] is not None and args.bisect:
        report['minimal_pair']=bisect(pieces,labels,report['first_empty_fuse'])
    if report['first_empty_fuse'] is None:
        whole=shapes[0][0];report['union']=mass(whole)
        for n,((x,y),via) in enumerate(via_intervals.items()):
            nxt=whole-Cylinder(Pnt(x,y,via['low']),Dir(0,0,1),spec['via_inner_radius_m'],via['high']-via['low'])
            if not mass(nxt)[0]:report['first_empty_drill']=dict(index=n,xy=[x,y],before=mass(whole));break
            whole=nxt
        report['drilled']=mass(whole)
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='scope'},default=str)[:3000])


if __name__=='__main__':main()
