#!/usr/bin/env python3
"""Apply separate-body exact stress controls to the fixed upstream-style PM case.

Uses completed bare/nonlinear finite_plate jobs and an already archived raw
field report. No model fit, new solve, nodal smoothing or self-force subtraction.
This adds force controls; it does not qualify motor housing motion or winding
forces. The fixed geometry is scripts/solvers/finite_plate.geo.
"""
import argparse
import json
from pathlib import Path

from cut_surface_force import box_force
from post_project_balance import action_reaction
from post_project_force import sha
from project_static import check_force_paths,getdp_nonlinear_convergence
from check_finite_plate import require_elmer_nonlinear_convergence
from read_vtu import _vector_mesh,clear_vector_cache
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--field-report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('preserve earlier audits')
    summary=work/'summary.json';source=json.loads(summary.read_text());raw_report=json.loads(args.field_report.read_text())
    if source.get('status')!='comparison-only' or source.get('failures') or raw_report.get('status')!='comparison-only':
        raise ValueError('Need completed original finite plate and raw field reports')
    if sha(summary)!=raw_report['source_summary_sha256']:raise ValueError('Raw field report references a different original solve')
    request=source['request'];backend=request['backend'];paths={}
    if backend not in ['getdp','elmer']:raise ValueError('Unknown original backend')
    if backend=='elmer' and raw_report.get('field_representation')!='element':raise ValueError('Refuse nodal smoothing across interfaces')
    for name in ['bare','nonlinear']:
        job=work/name;receipt=json.loads((job/'solve.log.command.json').read_text())
        if receipt.get('status')!='completed' or receipt.get('exit_code')!=0:raise ValueError('Incomplete original solve')
        for rel,digest in source['runs'][name]['input_sha256'].items():
            if sha(job/rel)!=digest:raise ValueError('Original finite-plate input changed')
        if backend=='getdp':
            path=job/'raw-air-force'/'air.pos';post=json.loads((path.parent/'post.log.command.json').read_text())
            if post.get('status')!='completed' or post.get('exit_code')!=0:raise ValueError('Incomplete field export')
        else:
            candidates=list(job.glob('**/fields*.vtu'))
            if len(candidates)!=1:raise ValueError('Missing or ambiguous raw field')
            path=candidates[0]
        if sha(path)!=raw_report['air_field_sha256'][name]:raise ValueError('Original raw field changed')
        paths[name]=path
    proof=getdp_nonlinear_convergence(work/'nonlinear') if backend=='getdp' else require_elmer_nonlinear_convergence((work/'nonlinear'/'solve.log').read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sources=capture(args.output.parent,[Path(__file__),*[Path(__file__).parent/name for name in
        ['cut_surface_force.py','post_project_balance.py','post_project_force.py','project_static.py','check_finite_plate.py','read_vtu.py']]])
    report={'scope':__doc__,'status':'running','backend':backend,'request':request,'nonlinear_convergence':proof,
            'source_summary_sha256':sha(summary),'field_report_sha256':sha(args.field_report),
            'raw_field_sha256':{name:sha(path) for name,path in paths.items()},'source_snapshots':sources,
            'cases':{},'action_reaction':{},'failures':[]}
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    clearances=[0.0004,0.0006,0.0008]
    for name,path in paths.items():
        clear_vector_cache();stat=path.stat()
        vertices,fields,*_=_vector_mesh(str(path.resolve()),stat.st_mtime_ns,stat.st_size,'magnetic flux density e')
        bodies={}
        for body,low,high in [('stator',[-0.006,-0.006,-request['thickness']],[0.006,0.006,0]),
                              ('mover',[-0.0025,-0.0025,0.0013],[0.0025,0.0025,0.0043])]:
            results={}
            for c in clearances:
                results[str(c)]=box_force(vertices,fields,[v-c for v in low],[v+c for v in high])
                print(name,body,c,results[str(c)]['force_n'],flush=True)
            bodies[body]=results
        report['cases'][name]=bodies;save();del vertices,fields
    for body in ['stator','mover']:
        controls={mode:{'stack_force_by_clearance_n':{c:v['force_n'] for c,v in report['cases'][name][body].items()}}
                  for mode,name in [('bare','bare'),('stack','nonlinear')]}
        report['failures'].extend(body+': '+failure for failure in check_force_paths(controls))
    for c in map(str,clearances):
        check=action_reaction(report['cases']['nonlinear']['stator'][c]['force_n'],report['cases']['nonlinear']['mover'][c]['force_n'])
        report['action_reaction'][c]=check
        if not check['passed']:report['failures'].append(c+': direct action/reaction exceeds max(10nN, 2%)')
    if sha(summary)!=report['source_summary_sha256'] or sha(args.field_report)!=report['field_report_sha256']:
        raise ValueError('Input report changed during audit')
    for name,path in paths.items():
        if sha(path)!=report['raw_field_sha256'][name]:raise ValueError('Raw field changed during audit')
    for path,entry in sources.items():
        if sha(Path(path))!=entry['sha256']:raise ValueError('Audit source changed during validation')
    report['status']='failed' if report['failures'] else 'passed-exact-finite-plate-force-controls-only';save()
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':main()
