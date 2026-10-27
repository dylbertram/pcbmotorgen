#!/usr/bin/env python3
"""Audit completed finite-plate mesh/domain/surface/quadrature comparisons.

All gates are numerical checks for this fixed magnetostatic diagnostic. Passing
does not qualify material provenance, moving eddy currents or arbitrary housing.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import magpylib as magpy
from check_finite_plate import OBSERVATIONS


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_refinement(requests):
    coarse,fine,domain=(requests[tag] for tag in ['coarse','fine','domain'])
    for key in ['mesh','gap_mesh','radius']:
        if any(not np.isfinite(r[key]) or r[key]<=0 for r in [coarse,fine,domain]):
            raise ValueError('Invalid refinement dimensions')
    if not (fine['mesh']<coarse['mesh'] and fine['gap_mesh']<coarse['gap_mesh'] and fine['radius']==coarse['radius']):
        raise ValueError('Mesh study must refine solid and gap with unchanged outer domain')
    if not (domain['mesh']==fine['mesh'] and domain['gap_mesh']==fine['gap_mesh'] and domain['radius']>fine['radius']):
        raise ValueError('Domain study must expand the air domain without changing the near mesh')


def load(work, summary_name):
    path=work/summary_name
    report=json.loads(path.read_text())
    if report.get('status')!='comparison-only' or report.get('failures'):
        raise ValueError(f'Incomplete or failed finite diagnostic: {path}')
    fields={}
    for name in ['bare','linear','nonlinear']:
        run=report['runs'][name]
        for file,checksum in run.get('input_sha256',run.get('sha256',{})).items():
            if digest(work/name/file)!=checksum:
                raise ValueError(f'Changed archived input/output: {work/name/file}')
        file=work/name/('postprocessed-field.txt' if summary_name=='postprocessed-summary.json' else 'field.txt')
        fields[name]=np.loadtxt(file)
        if fields[name].shape!=(25,6) or not np.isfinite(fields[name]).all():
            raise ValueError(f'Invalid field table: {file}')
        np.testing.assert_allclose(fields[name][:,:3],OBSERVATIONS,atol=1e-14,rtol=0)
        if abs(fields[name][12,5]-run['centre_bz_t'])>1e-10:
            raise ValueError('Field table does not match the archived result')
    magnet=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028))
    expected=magnet.getB(OBSERVATIONS)
    if np.linalg.norm(fields['bare'][:,3:]-expected)/np.linalg.norm(expected)>0.05:
        raise ValueError('Bare Magpylib field gate failed on archived samples')
    return report,fields


def force_report(work, source, subdivisions):
    prefix='force-element' if source['request']['backend']=='elmer' else 'force'
    path=work/f'{prefix}-n{subdivisions}.json'
    report=json.loads(path.read_text())
    if report.get('status')!='comparison-only' or report.get('subdivisions')!=subdivisions:
        raise ValueError(f'Incomplete force quadrature: {path}')
    if set(report['surfaces'])!={'0.0004','0.0006','0.0008'}:
        raise ValueError(f'Missing air surfaces: {path}')
    for runs in report['surfaces'].values():
        if set(runs)!={'bare','linear','nonlinear'}:raise ValueError('Missing force case')
        for mode,v in runs.items():
            if np.asarray(v).shape!=(3,) or not np.isfinite(v).all():raise ValueError('Invalid force vector')
            if mode!='bare' and v[2]<=0:raise ValueError('Expected attraction toward the magnet')
    return report


def assess(fields, forces):
    failures=[]
    changes={}
    for label,first,second in [('mesh','coarse','fine'),('domain','fine','domain')]:
        changes[label]={}
        for mode in ['bare','linear','nonlinear']:
            a,b=fields[first][mode],fields[second][mode]
            if not np.isfinite(a).all() or not np.isfinite(b).all() or np.linalg.norm(b[:,3:])<=1e-12:
                raise ValueError('Invalid or unresolved field comparison')
            np.testing.assert_allclose(a[:,:3],b[:,:3],atol=1e-14,rtol=0)
            change=float(np.linalg.norm(a[:,3:]-b[:,3:])/np.linalg.norm(b[:,3:]))
            changes[label][mode]={'field_vector_change':change}
            if change>0.02:failures.append(f'{label} {mode} field change {change:.2%} exceeds 2%')
            if mode!='bare':
                x=forces[first][64]['surfaces']['0.0006'][mode][2]
                y=forces[second][64]['surfaces']['0.0006'][mode][2]
                delta=abs(x/y-1)
                changes[label][mode]['normal_force_change']=delta
                if delta>0.02:failures.append(f'{label} {mode} force change {delta:.2%} exceeds 2%')
    for tag in ['fine','domain']:
        scale=abs(forces[tag][64]['surfaces']['0.0006']['nonlinear'][2])
        if not np.isfinite(scale) or scale<=1e-9:
            raise ValueError('No resolved nonlinear normal force')
        for clearance,runs in forces[tag][64]['surfaces'].items():
            for mode,v in runs.items():
                v=np.asarray(v)
                if v.shape!=(3,) or not np.isfinite(v).all():raise ValueError('Invalid force vector')
                if mode=='bare':
                    if np.linalg.norm(v)>0.02*scale:failures.append(f'{tag} {clearance}: empty-box force floor exceeds 2%')
                else:
                    if np.linalg.norm(v[:2])>0.02*abs(v[2]):failures.append(f'{tag} {mode} {clearance}: transverse symmetry error exceeds 2%')
                    centre=forces[tag][64]['surfaces']['0.0006'][mode][2]
                    if abs(v[2]/centre-1)>0.02:failures.append(f'{tag} {mode}: air-surface sensitivity exceeds 2%')
                    previous=forces[tag][32]['surfaces'][clearance][mode][2]
                    if abs(previous/v[2]-1)>0.02:failures.append(f'{tag} {mode}: force quadrature change exceeds 2%')
    return changes,failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for tag in ['coarse','fine','domain']:
        parser.add_argument('--'+tag+'-work',type=Path,required=True)
        parser.add_argument('--'+tag+'-summary',default='summary.json')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    sources={};fields={};forces={};hashes={}
    for tag in ['coarse','fine','domain']:
        work=getattr(args,tag+'_work').resolve()
        summary=getattr(args,tag+'_summary')
        sources[tag],fields[tag]=load(work,summary)
        forces[tag]={n:force_report(work,sources[tag],n) for n in ([64] if tag=='coarse' else [32,64])}
        for report in forces[tag].values():
            if report['source_summary_sha256']!=digest(work/summary):
                raise ValueError('Force report belongs to a different field solve')
        if tag!='coarse':
            if sources[tag]['runs']['bare']['magpylib_vector_error']>0.05:
                raise ValueError('Bare Magpylib field gate failed')
        hashes[tag]={'summary':digest(work/summary),'geometry':digest(work/'finite_plate.geo')}
        prefix='force-element' if sources[tag]['request']['backend']=='elmer' else 'force'
        for n in forces[tag]:hashes[tag][f'force_n{n}']=digest(work/f'{prefix}-n{n}.json')
        for mode in fields[tag]:
            field='postprocessed-field.txt' if summary=='postprocessed-summary.json' else 'field.txt'
            hashes[tag][f'field_{mode}']=digest(work/mode/field)
    for tag in ['fine','domain']:
        for key in ['backend','thickness','mu','bsat']:
            if sources[tag]['request'][key]!=sources['coarse']['request'][key]:raise ValueError('Physics input mismatch')
        if hashes[tag]['geometry']!=hashes['coarse']['geometry']:raise ValueError('Geometry source changed')
    validate_refinement({tag:source['request'] for tag,source in sources.items()})
    changes,failures=assess(fields,forces)
    result={'scope':__doc__,'status':'failed' if failures else 'passed','backend':sources['fine']['request']['backend'],
            'changes':changes,'failures':failures,'source_sha256':hashes,'analysis_sha256':digest(Path(__file__))}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    if failures:raise SystemExit('\n'.join(failures))
    print('PASS: finite magnetostatic field/force mesh, domain, air-surface, symmetry and quadrature gates')


if __name__=='__main__':
    main()
