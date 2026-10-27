#!/usr/bin/env python3
"""Independently integrate stator and mover forces from completed raw fields.

The mover force is not the negated stator force. Test both empty-box/self-force
floors, three closed-air paths, direct action/reaction and separate quadrature
refinement. Does not qualify mesh/domain convergence, motion or winding thrust.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from maxwell_stress import box_faces,force
from post_project_force import completed_field
from project_static import check_force_paths,getdp_nonlinear_convergence,validate_mesh
from project_symmetry import mirrored_sample,quarter_model,validate_quarter_mesh
from read_vtu import sample_vector,clear_vector_cache
from source_snapshot import capture


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bounds(objects):
    low=np.min([o['origin_m'] for o in objects],axis=0)
    high=np.max([np.asarray(o['origin_m'])+o['size_m'] for o in objects],axis=0)
    if not np.isfinite([low,high]).all() or np.any(high<=low):raise ValueError('Invalid body bounds')
    return low,high


def surfaces(objects,clearance,n,radius):
    low,high=bounds(objects);centre=(low+high)/2;half=(high-low)/2
    far=np.maximum(abs(low-clearance),abs(high+clearance))
    if np.linalg.norm(far)>=0.95*radius:
        raise ValueError('Force surface approaches the exterior boundary; enlarge air domain')
    faces=box_faces(half[0]+clearance,low[2]-clearance,high[2]+clearance,n,halfdepth=half[1]+clearance)
    shift=np.array([centre[0],centre[1],0.])
    faces=[(points+shift,normal,area) for points,normal,area in faces]
    return faces


def action_reaction(stator,mover):
    a=np.asarray(stator);b=np.asarray(mover)
    if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite([a,b]).all():raise ValueError('Invalid body force vectors')
    error=float(np.linalg.norm(a+b));scale=max(float(np.linalg.norm(a)),float(np.linalg.norm(b)))
    if not np.isfinite([error,scale]).all():raise ValueError('Nonfinite force norms')
    limit=max(1e-8,0.02*scale)
    return {'imbalance_n':error,'limit_n':limit,'passed':error<=limit}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--subdivisions',type=int,nargs='+',default=[64,128])
    parser.add_argument('--clearance-mm',type=float,nargs=3,default=[0.1,0.2,0.3])
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('preserve previous force-balance reports')
    if len(args.subdivisions)<2 or any(not 2<=n<=512 for n in args.subdivisions) or any(a>=b for a,b in zip(args.subdivisions,args.subdivisions[1:])):
        parser.error('provide independent increasing quadrature levels between 2 and 512')
    clearances=np.asarray(args.clearance_mm)*1e-3
    if not np.isfinite(clearances).all() or clearances[0]<=0 or np.any(np.diff(clearances)<=0):parser.error('three increasing positive clearances required')
    source,raw_bare=completed_field(work,'bare');_,raw_stack=completed_field(work,'stack')
    model=source['model']
    if not model['stack']:parser.error('need a finite stator stack')
    if source.get('quarter_symmetry',False):
        if source.get('backend')!='getdp' or source.get('solver_geometry_model')!=quarter_model(model):
            raise ValueError('Invalid quarter-domain geometry metadata')
        validate_mesh(work/'project.msh',source['solver_geometry_model'],source['air_radius_m'])
        validate_quarter_mesh(work/'project.msh')
    if max(clearances)>=bounds(model['magnets'])[0][2]-bounds(model['stack'])[1][2]:
        parser.error('force boxes intersect the other body; reduce clearances')
    if source.get('backend')=='getdp':getdp_nonlinear_convergence(work/'stack')
    reader=mirrored_sample if source.get('quarter_symmetry',False) else sample_vector
    args.output.parent.mkdir(parents=True,exist_ok=True)
    paths=[Path(__file__),*[Path(__file__).parent/name for name in ['project_static.py','project_symmetry.py','post_project_force.py','read_vtu.py','maxwell_stress.py']]]
    snapshots=capture(args.output.parent,paths)
    report={'scope':__doc__,'status':'running','source_summary_sha256':sha(work/'summary.json'),
            'raw_field_sha256':{'bare':sha(raw_bare),'stack':sha(raw_stack)},'quarter_symmetry':bool(source.get('quarter_symmetry',False)),
            'levels':{},'failures':[],'source_snapshots':snapshots}
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();previous=None
    for n in args.subdivisions:
        level={'bare':{},'stack':{},'action_reaction':{}}
        for case,raw in [('bare',raw_bare),('stack',raw_stack)]:
            clear_vector_cache()
            for group,objects in [('stator',model['stack']),('mover',model['magnets'])]:
                result={}
                for clearance in clearances:
                    faces=surfaces(objects,float(clearance),n,source['air_radius_m'])
                    vector=force(faces,[reader(raw,points,'magnetic flux density e') for points,_,_ in faces])
                    if not np.isfinite(vector).all() or not np.isfinite(np.linalg.norm(vector)):raise ValueError('Nonfinite reconstructed force')
                    result[str(float(clearance))]=vector.tolist()
                level[case][group]=result
        for group in ['stator','mover']:
            controls={case:{'stack_force_by_clearance_n':level[case][group]} for case in ['bare','stack']}
            for error in check_force_paths(controls):report['failures'].append(f'n={n} {group}: {error}')
        for clearance in level['stack']['stator']:
            check=action_reaction(level['stack']['stator'][clearance],level['stack']['mover'][clearance])
            level['action_reaction'][clearance]=check
            if not check['passed']:report['failures'].append(f'n={n} clearance={clearance}: direct action/reaction exceeds max(10nN, 2%)')
        if previous:
            changes={}
            for case in ['bare','stack']:
                for group in ['stator','mover']:
                    a=np.array(list(previous[case][group].values()));b=np.array(list(level[case][group].values()))
                    difference=np.linalg.norm(a-b,axis=1)
                    reference=np.array(list(level['stack'][group].values()))
                    limits=np.maximum(1e-8,0.02*np.linalg.norm(reference,axis=1))
                    changes[case+'/'+group]={'absolute_changes_n':difference.tolist(),'limits_n':limits.tolist()}
                    if np.any(difference>limits):report['failures'].append(f'n={n}: {case}/{group} quadrature change exceeds max(10nN, 2% of body force)')
            level['quadrature_changes']=changes
        report['levels'][str(n)]=level;previous=level;save()
        print('quadrature',n,'action/reaction',level['action_reaction'],flush=True)
    for path in paths:
        if sha(path)!=snapshots[str(path.resolve())]['sha256']:raise ValueError('Postprocessor source changed during audit')
    if sha(work/'summary.json')!=report['source_summary_sha256'] or sha(raw_bare)!=report['raw_field_sha256']['bare'] or sha(raw_stack)!=report['raw_field_sha256']['stack']:
        raise ValueError('Raw inputs changed during force audit')
    report['status']='failed' if report['failures'] else 'passed-closed-surface-balance-numerics-only';save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
