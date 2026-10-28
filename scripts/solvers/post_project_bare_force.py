#!/usr/bin/env python3
"""Measure near-PM self-force error before an expensive nonlinear material job.

No stack force is available here, so no relative material-force gate or accepted
finite-array prediction is inferred. Raw completion receipts, field hashes,
physical geometry and full closed-face coverage are still mandatory.
"""
import argparse
import json
import math
from pathlib import Path

from cut_surface_force import box_force,reflected_tetrahedra
from post_project_force import completed_field,sha
from post_project_balance import bounds
from project_static import validate_mesh
from project_symmetry import quarter_model,validate_quarter_mesh
from read_vtu import _vector_mesh
from source_snapshot import capture


def require_bare_control(source):
    if source.get('status')!='completed-bare-field-only-unqualified' or source.get('failures')!=[]:
        raise ValueError('Need a completed explicit bare-only field control, not a partial/failed material study')
    error=source.get('runs',{}).get('bare',{}).get('magpylib_vector_error')
    if isinstance(error,bool) or not isinstance(error,(int,float)) or not math.isfinite(error) or not 0<=error<=0.05:
        raise ValueError('Missing or failed independent bare field check')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('preserve existing force diagnostics')
    source,field=completed_field(work,'bare');require_bare_control(source)
    model=source['model'];quarter=bool(source.get('quarter_symmetry',False))
    solver_model=quarter_model(model) if quarter else model
    if quarter and source.get('solver_geometry_model')!=solver_model:raise ValueError('Changed symmetry geometry metadata')
    validate_mesh(work/'project.msh',solver_model,source['air_radius_m'])
    if quarter:validate_quarter_mesh(work/'project.msh')
    summary_hash=sha(work/'summary.json');field_hash=sha(field)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    paths=[Path(__file__),*[Path(__file__).parent/name for name in ['cut_surface_force.py','post_project_force.py','post_project_balance.py','project_static.py','project_symmetry.py','read_vtu.py']]]
    sources=capture(args.output.parent,paths)
    stat=field.stat();vertices,vectors,*_=_vector_mesh(str(field.resolve()),stat.st_mtime_ns,stat.st_size,'magnetic flux density e')
    if quarter:vertices,vectors=reflected_tetrahedra(vertices,vectors)
    lower,upper=bounds(model['magnets']);surfaces={}
    for c in [0.0001,0.0002,0.0003]:
        if model['stack'] and lower[2]-c<=bounds(model['stack'])[1][2]:raise ValueError('Force box intersects the other material geometry')
        surfaces[str(c)]=box_force(vertices,vectors,lower-c,upper+c)
        print(c,surfaces[str(c)]['force_n'],flush=True)
    if sha(work/'summary.json')!=summary_hash or sha(field)!=field_hash:raise ValueError('Source fields changed during audit')
    for path in paths:
        if sha(path)!=sources[str(path.resolve())]['sha256']:raise ValueError('Audit implementation changed during validation')
    report={'scope':__doc__,'status':'completed-bare-self-force-diagnostic-unqualified','source_summary_sha256':summary_hash,
            'raw_field_sha256':field_hash,'magpylib_vector_error':source['runs']['bare']['magpylib_vector_error'],
            'surfaces':surfaces,'source_snapshots':sources}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
