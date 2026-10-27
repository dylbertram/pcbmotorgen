#!/usr/bin/env python3
"""Independent analytic check that exact copper CAD keeps every declared primitive.

Pairwise OCC fusion can silently drop volume. This re-derives the same declared
straight trace boxes, end discs, via barrels, pads and drill bores analytically
from the saved fixture, estimates their exact union by unbiased Monte Carlo and
compares it with the BRep volume. With --mesh-work it also requires each
primitive's interior samples to lie inside the solved conductor mesh.
No geometry is repaired or substituted; native arcs are rejected, not approximated.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from finite_copper_geometry import dimensions
from post_project_force import sha
from winding_oracle import edge_points,layer_z

VOLUME_GATE=.005
STANDARD_ERROR_GATE=.001
COVERAGE_GATE=.99


def primitives(fixture,shift):
    """Declared solids in exact build order, plus drill bores removed afterwards."""
    spec=dimensions(fixture);shift=np.asarray(shift,dtype=float);layers={x['layer']:x for x in spec['layers']}
    pieces=[];bores={}
    for network in fixture['networks']:
        for index,edge in enumerate(network['edges']):
            geometry=edge['geometry'];points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            if geometry['kind']=='trace':
                if 'circular_arc_m' in geometry:raise ValueError('Native arcs are outside this straight-copper audit')
                layer=layers[geometry['layer']];width,thickness=layer['trace_width_m'],layer['thickness_m'];z=points[0,2]-thickness/2
                for a,b in zip(points[:-1],points[1:]):
                    pieces.append(dict(kind='segment',a=a[:2],b=b[:2],half_width=width/2,z=(z,z+thickness),label=f"segment:{network['net']}:{index}"))
                for point in points:
                    pieces.append(dict(kind='annulus',centre=point[:2],radii=(0.,width/2),z=(z,z+thickness),label=f"cap:{network['net']}:{index}"))
            elif geometry['kind']=='via':
                pair=geometry['layers']
                low=min(layer_z(fixture['sim'],fixture['geometry_hints'],l)-layers[l]['thickness_m']/2 for l in pair)+shift[2]
                high=max(layer_z(fixture['sim'],fixture['geometry_hints'],l)+layers[l]['thickness_m']/2 for l in pair)+shift[2]
                entry=bores.setdefault(tuple(points[0,:2]),dict(low=low,high=high,layers=set()))
                entry['low']=min(entry['low'],low);entry['high']=max(entry['high'],high);entry['layers'].update(pair)
            else:raise ValueError('Unsupported exported copper edge')
    for (x,y),via in bores.items():
        centre=np.array([x,y])
        pieces.append(dict(kind='annulus',centre=centre,radii=(spec['via_inner_radius_m'],spec['via_outer_radius_m']),z=(via['low'],via['high']),label=f'barrel:{x:.6g}:{y:.6g}'))
        for index in sorted(via['layers']):
            layer=layers[index];z=layer['centre_z_m']+shift[2]-layer['thickness_m']/2
            pieces.append(dict(kind='annulus',centre=centre,radii=(spec['via_inner_radius_m'],spec['via_pad_radius_m']),z=(z,z+layer['thickness_m']),label=f'pad:{x:.6g}:{y:.6g}:{index}'))
    drills=[dict(kind='annulus',centre=np.array(key),radii=(0.,spec['via_inner_radius_m']),z=(via['low'],via['high'])) for key,via in bores.items()]
    return pieces,drills


def piece_volume(piece):
    height=piece['z'][1]-piece['z'][0]
    if piece['kind']=='segment':return float(np.linalg.norm(piece['b']-piece['a'])*2*piece['half_width']*height)
    inner,outer=piece['radii'];return float(np.pi*(outer**2-inner**2)*height)


def contains(piece,points,margin=0.):
    z=points[:,2];inside=(z>=piece['z'][0]+margin)&(z<=piece['z'][1]-margin)
    if piece['kind']=='segment':
        a,b=piece['a'],piece['b'];axis=b-a;length=np.linalg.norm(axis);axis=axis/length;normal=np.array([-axis[1],axis[0]])
        relative=points[:,:2]-a;along=relative@axis;across=relative@normal
        return inside&(along>=margin)&(along<=length-margin)&(np.abs(across)<=piece['half_width']-margin)
    radius=np.linalg.norm(points[:,:2]-piece['centre'],axis=1);inner,outer=piece['radii']
    return inside&(radius<=outer-margin)&((radius>=inner+margin) if inner>0 else True)


def sample(piece,count,rng,margin=0.):
    z=rng.uniform(piece['z'][0]+margin,piece['z'][1]-margin,count)
    if piece['kind']=='segment':
        a,b=piece['a'],piece['b'];axis=b-a;length=np.linalg.norm(axis);axis=axis/length;normal=np.array([-axis[1],axis[0]])
        along=rng.uniform(margin,length-margin,count);across=rng.uniform(-piece['half_width']+margin,piece['half_width']-margin,count)
        return np.column_stack([a+np.outer(along,axis)+np.outer(across,normal),z])
    inner,outer=piece['radii'];inner=inner+margin if inner>0 else 0.;outer-=margin
    radius=np.sqrt(rng.uniform(inner**2,outer**2,count));angle=rng.uniform(0,2*np.pi,count)
    return np.column_stack([piece['centre']+np.column_stack([np.cos(angle),np.sin(angle)])*radius[:,None],z])


def bounds(piece):
    if piece['kind']=='segment':
        xy=np.vstack([piece['a'],piece['b']]);low,high=xy.min(axis=0)-piece['half_width'],xy.max(axis=0)+piece['half_width']
    else:low,high=piece['centre']-piece['radii'][1],piece['centre']+piece['radii'][1]
    return np.r_[low,piece['z'][0]],np.r_[high,piece['z'][1]]


def union_estimate(pieces,drills,samples,seed=20261022):
    rng=np.random.default_rng(seed);boxes=[bounds(p) for p in pieces+drills];low=np.array([b[0] for b in boxes]);high=np.array([b[1] for b in boxes])
    total=0.;variance=0.;n=len(pieces)
    for i,piece in enumerate(pieces):
        points=sample(piece,samples,rng);near=np.flatnonzero(np.all((low<=high[i])&(high>=low[i]),axis=1))
        count=np.zeros(samples);drilled=np.zeros(samples,dtype=bool)
        for j in near:
            if j<n:count+=contains(pieces[j],points,-1e-12)
            else:drilled|=contains(drills[j-n],points)
        if np.any(count<1):raise ValueError('Primitive sampler produced points outside its own primitive')
        weight=np.where(drilled,0.,1/count);volume=piece_volume(piece)
        total+=volume*weight.mean();variance+=volume**2*weight.var(ddof=1)/samples
    return total,float(np.sqrt(variance))


def mesh_coverage(pieces,drills,mesh,samples,margin,seed=20261023):
    rng=np.random.default_rng(seed);result=[]
    for piece in pieces:
        points=sample(piece,samples,rng,margin);keep=~np.any([contains(d,points,-margin) for d in drills],axis=0)
        points=points[keep]
        if len(points)<samples//4:continue
        located=mesh(points[:,0],points[:,1],points[:,2]);fraction=float(np.mean(located['nr']>=0))
        result.append(dict(label=piece['label'],samples=int(len(points)),inside_fraction=fraction,passed=bool(fraction>=COVERAGE_GATE)))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copper-work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mesh-work',type=Path,help='completed source solve on this exact copper; checks primitive coverage')
    parser.add_argument('--samples',type=int,default=4000);parser.add_argument('--coverage-samples',type=int,default=400)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous union audits')
    work=args.copper_work.resolve();summary=json.loads((work/'summary.json').read_text())
    fixtures=[Path(p) for p in summary['input_hashes'] if p.endswith('/fixture.json')]
    if len(fixtures)!=1 or sha(fixtures[0])!=summary['input_hashes'][str(fixtures[0])]:raise ValueError('Unique unchanged saved fixture required')
    pieces,drills=primitives(json.loads(fixtures[0].read_text()),summary['translation_m'])
    estimate,error=union_estimate(pieces,drills,args.samples);cad=summary['geometry']['volume_m3']
    report=dict(scope=__doc__,copper_work=str(work),summary_sha256=sha(work/'summary.json'),brep_sha256=summary.get('brep_sha256'),
        fixture_sha256=sha(fixtures[0]),primitives=len(pieces),drill_bores=len(drills),samples_per_primitive=args.samples,
        analytic_union_volume_m3=estimate,analytic_standard_error_m3=error,cad_volume_m3=cad,
        relative_difference=abs(cad/estimate-1) if estimate>0 else None,volume_gate=VOLUME_GATE,standard_error_gate=STANDARD_ERROR_GATE,
        sum_of_primitive_volumes_m3=float(sum(piece_volume(p) for p in pieces)))
    failures=[]
    if error/estimate>STANDARD_ERROR_GATE:failures.append('analytic estimate not resolved to declared standard error')
    if not cad or report['relative_difference']>VOLUME_GATE:failures.append('CAD volume differs from analytic declared union')
    if args.mesh_work:
        import ngsolve as ng
        source=json.loads((args.mesh_work.resolve()/'summary.json').read_text())
        if str(work/'copper.brep') not in source['input_hashes'] or sha(work/'copper.brep')!=source['input_hashes'][str(work/'copper.brep')]:
            raise ValueError('Mesh work was not solved on this exact copper')
        if sha(args.mesh_work.resolve()/'mesh.vol')!=source['mesh_sha256']:raise ValueError('Source mesh changed')
        margin=.1*min(min(p['z'][1]-p['z'][0] for p in pieces),min(p.get('half_width',np.inf) for p in pieces))
        coverage=mesh_coverage(pieces,drills,ng.Mesh(str(args.mesh_work.resolve()/'mesh.vol')),args.coverage_samples,margin)
        report.update(mesh_work=str(args.mesh_work.resolve()),mesh_sha256=source['mesh_sha256'],coverage_margin_m=margin,coverage_gate=COVERAGE_GATE,
            covered_primitives=len(coverage),minimum_inside_fraction=min(c['inside_fraction'] for c in coverage),
            coverage_failures=[c for c in coverage if not c['passed']])
        if report['coverage_failures']:failures.append('declared primitive interior missing from solved conductor mesh')
    report.update(failures=failures,status='failed' if failures else 'passed-declared-primitive-union-volume-only')
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('scope','coverage_failures')}),flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
