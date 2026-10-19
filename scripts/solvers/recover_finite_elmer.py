#!/usr/bin/env python3
"""Reprocess finished Elmer jobs after a Python postprocessing failure.

Requires a normal solver finish, unchanged archived inputs and converged
nonlinear potential. Does not rescue a timeout or unconverged solution.
Writes a separate report and never changes the original input or log files.
"""
import argparse
import hashlib
import json
from pathlib import Path

import magpylib as magpy
import numpy as np

from check_finite_plate import OBSERVATIONS, validate_mesh, require_elmer_nonlinear_convergence
from read_vtu import sample_vector


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    work=args.work.resolve()
    source=work/'summary.json'
    original=json.loads(source.read_text())
    request=original['request']
    if request['backend'] != 'elmer':
        parser.error('Elmer jobs required')
    volumes=validate_mesh(work/'plate.msh',request['thickness'],request['radius'])
    report={'scope':'finite 3D magnetostatic fields only; recovered postprocessing, not physics refinement',
            'status':'running','request':request,'source_summary_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'material_volumes_m3':volumes,'runs':{}}
    destination=work/'postprocessed-summary.json'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    failures=[]
    reference=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028)).getB(OBSERVATIONS)
    for mode,name in enumerate(['bare','linear','nonlinear']):
        job=work/name
        archived=json.loads((job/'request.json').read_text())
        assert archived.pop('mode') == mode and archived == request, 'Mismatched archived request'
        assert hashlib.sha256((job/'plate.msh').read_bytes()).hexdigest() == original['mesh_sha256']
        if name in original['runs']:
            for file,digest in original['runs'][name]['input_sha256'].items():
                assert hashlib.sha256((job/file).read_bytes()).hexdigest()==digest, f'Changed input {file}'
        log=(job/'solve.log').read_text()
        assert 'ELMER SOLVER FINISHED AT:' in log and not any(marker in log for marker in ['FAILED:','ERROR::','NOT CONVERGED']), 'Incomplete or failed solver log'
        result={}
        if mode==2:
            result['nonlinear_convergence']=require_elmer_nonlinear_convergence(log)
        files=list(job.glob('**/fields*.vtu'))
        assert len(files)==1,files
        b=sample_vector(files[0],OBSERVATIONS)
        np.savetxt(job/'postprocessed-field.txt',np.column_stack([OBSERVATIONS,b]))
        result['centre_bz_t']=float(b[12,2])
        if mode==0:
            result['magpylib_vector_error']=float(np.linalg.norm(b-reference)/np.linalg.norm(reference))
            if result['magpylib_vector_error']>0.05: failures.append('Bare vector field error exceeds 5%')
        else:
            result['centre_gain']=result['centre_bz_t']/report['runs']['bare']['centre_bz_t']
        paths=[job/p for p in ['case.sif','HB','request.json','solve.log','plate.msh']]+files
        result['sha256']={str(p.relative_to(job)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        report['runs'][name]=result
        print(name,json.dumps(result),flush=True)
        destination.write_text(json.dumps(report,indent=2)+'\n')
    report['failures']=failures
    report['status']='failed' if failures else 'comparison-only'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    if failures: raise SystemExit('\n'.join(failures))


if __name__=='__main__':
    main()
