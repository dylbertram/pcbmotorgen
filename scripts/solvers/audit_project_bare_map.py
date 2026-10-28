#!/usr/bin/env python3
"""Independent prescribed-PM field maps around the finite magnet array.

Tests off-symmetry X/Y points on all three near-magnet force-plane heights,
not only a centreline with symmetry-forced components. By default, maps are
below the PM bottoms; --both-sides additionally maps above the PM tops.
This is analytical
free-space equivalence with Magpylib, not soft-material or force qualification.
"""
import argparse
import json
from pathlib import Path

import magpylib as magpy
import numpy as np

from post_project_force import completed_field,sha
from project_static import validate_mesh
from project_symmetry import quarter_model,validate_quarter_mesh,mirrored_sample
from read_vtu import sample_vector
from source_snapshot import capture


def observations(model,nx,ny,both_sides=False):
    if isinstance(nx,bool) or isinstance(ny,bool) or not isinstance(nx,int) or not isinstance(ny,int) or not 8<=nx<=512 or not 4<=ny<=256:
        raise ValueError('Choose finite field-map dimensions in the documented range')
    magnets=model['magnets'];low=np.min([o['origin_m'] for o in magnets],axis=0)
    high=np.max([np.asarray(o['origin_m'])+o['size_m'] for o in magnets],axis=0)
    if not np.isfinite([low,high]).all() or np.any(high<=low):raise ValueError('Invalid finite source bounds')
    xs=np.linspace(low[0]-0.0003,high[0]+0.0003,nx+1);ys=np.linspace(low[1]-0.0003,high[1]+0.0003,ny+1)
    x,y=np.meshgrid((xs[1:]+xs[:-1])/2,(ys[1:]+ys[:-1])/2,indexing='ij')
    planes={}
    for c in [0.0001,0.0002,0.0003]:
        z=low[2]-c
        if model['stack'] and z<=max(o['origin_m'][2]+o['size_m'][2] for o in model['stack']):
            raise ValueError('Probe plane would intersect the stack geometry')
        planes[str(c)]=np.column_stack([x.ravel(),y.ravel(),np.full(nx*ny,z)])
        if both_sides:
            planes['above:'+str(c)]=np.column_stack([x.ravel(),y.ravel(),np.full(nx*ny,high[2]+c)])
    return planes


def compare(actual,expected):
    actual=np.asarray(actual,dtype=float);expected=np.asarray(expected,dtype=float)
    if actual.shape!=expected.shape or actual.ndim!=2 or actual.shape[1]!=3 or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError('Invalid bare field-map vectors')
    difference=actual-expected;reference=float(np.linalg.norm(expected))
    if reference<=0 or not np.isfinite(reference):raise ValueError('Missing nonzero independent source field')
    error=float(np.linalg.norm(difference)/reference)
    if not np.isfinite(error):raise ValueError('Nonfinite field-map comparison')
    return {'vector_relative_l2_error':error,'maximum_absolute_vector_error_t':float(np.linalg.norm(difference,axis=1).max()),
            'component_rms_error_t':np.sqrt(np.mean(difference*difference,axis=0)).tolist(),
            'reference_component_rms_t':np.sqrt(np.mean(expected*expected,axis=0)).tolist(),'passed':error<=0.05}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--nx',type=int,default=64);parser.add_argument('--ny',type=int,default=24)
    parser.add_argument('--both-sides',action='store_true',help='also map above the PM tops; this is separate from the archived below-only diagnostic')
    args=parser.parse_args();work=args.work.resolve();probes=args.output.with_suffix('.npz')
    if args.output.exists() or probes.exists():parser.error('preserve existing field-map diagnostics')
    source,field=completed_field(work,'bare')
    if source.get('status') not in ['comparison-only','completed-bare-field-only-unqualified'] or source.get('failures')!=[]:
        raise ValueError('Need a completed source job, not a partial or failed study')
    if sha(work/'project.msh')!=source.get('mesh_sha256'):raise ValueError('Original mesh changed')
    model=source['model'];quarter=bool(source.get('quarter_symmetry',False));solver_model=quarter_model(model) if quarter else model
    if quarter and source.get('solver_geometry_model')!=solver_model:raise ValueError('Changed mirror geometry metadata')
    validate_mesh(work/'project.msh',solver_model,source['air_radius_m'])
    if quarter:validate_quarter_mesh(work/'project.msh')
    planes=observations(model,args.nx,args.ny,args.both_sides)
    if any(np.linalg.norm(points,axis=1).max()>=0.95*source['air_radius_m'] for points in planes.values()):raise ValueError('Probe plane approaches exterior boundary')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sources=capture(args.output.parent,[Path(__file__),*[Path(__file__).parent/name for name in ['post_project_force.py','project_static.py','project_symmetry.py','read_vtu.py']]])
    summary_hash=sha(work/'summary.json');field_hash=sha(field)
    magnets=[magpy.magnet.Cuboid(dimension=o['size_m'],polarization=o['polarization_t'],position=np.asarray(o['origin_m'])+np.asarray(o['size_m'])/2) for o in model['magnets']]
    reader=mirrored_sample if quarter else sample_vector
    records={};raw={};failures=[]
    for i,(clearance,points) in enumerate(planes.items()):
        expected=sum(magnet.getB(points) for magnet in magnets);actual=reader(field,points,'magnetic flux density e')
        records[clearance]=compare(actual,expected)
        raw[f'points_{i}']=points;raw[f'magpylib_b_{i}']=expected;raw[f'fem_b_{i}']=actual
        if not records[clearance]['passed']:failures.append(clearance+': off-symmetry vector field differs by more than unchanged 5% gate')
        print(clearance,records[clearance],flush=True)
    for path,entry in sources.items():
        if sha(Path(path))!=entry['sha256']:raise ValueError('Field-map implementation changed during validation')
    if sha(work/'summary.json')!=summary_hash or sha(field)!=field_hash:raise ValueError('Source fields changed during audit')
    with probes.open('xb') as stream:np.savez_compressed(stream,**raw)
    report={'scope':__doc__,'status':'failed' if failures else 'passed-off-symmetry-bare-field-map-only','failures':failures,
            'source_summary_sha256':summary_hash,'raw_field_sha256':field_hash,'probe_archive_sha256':sha(probes),
            'magpylib_version':magpy.__version__,'dimensions':[args.nx,args.ny],'planes':records,'source_snapshots':sources}
    report['plane_sides']='above-and-below' if args.both_sides else 'below'
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
