#!/usr/bin/env python3
"""Emit the declared DC source-control campaign for one prepared linear copper case.

Uses only the source controls of the declared acceptance matrix: curvature,
mesh and drive-length axes around an explicit basis, all-eligible active
sections on every solve, then passive/return/H1/RT0 on the basis. Local
refinement comparisons and the choice of an accepted basis are audited after
the campaign; a failed basis is never replaced by an undeclared control.
"""
import argparse
import json
from pathlib import Path

ROOT=Path.home()/'.local/opt/solver-prototypes-macos'
SOURCE=['solve_linear_dc_study.py','finite_copper_circuit.py','finite_copper_curvature.py','finite_copper_current.py',
        'prepare_linear_dc_copper.py','finite_copper_geometry.py']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['prefix','copper-work','matrix','output','cutoff']:parser.add_argument('--'+key,required=True)
    parser.add_argument('--basis-curvature',type=float,required=True);parser.add_argument('--declared-no-stubs',action='store_true')
    parser.add_argument('--source-memory-gib',type=float,default=6.);parser.add_argument('--source-timeout',type=float,default=5400.)
    parser.add_argument('--max-dofs',type=int,default=24000000);parser.add_argument('--resistivity',type=float,required=True)
    parser.add_argument('--max-parallel',type=int,default=2);parser.add_argument('--memory-budget-gib',type=float,default=13.)
    args=parser.parse_args();matrix=json.loads(Path(args.matrix).read_text());controls=matrix['source_controls']
    coarse_mesh,fine_mesh=max(controls['mesh_m']),min(controls['mesh_m'])
    base_port,other_port=controls['port_fraction'][0],controls['port_fraction'][1]
    if args.basis_curvature not in controls['curvature_safety']:parser.error('Basis curvature must be a declared control')
    w=lambda name:str(ROOT/(args.prefix+name+'-v1-20261022'));jobs=[]
    def job(name,script_args,depends=(),inputs=(),timeout=1800.,memory=4.):
        jobs.append(dict(name=name,log=args.prefix+name+'-v1-20261022.log',args=script_args,depends=list(depends),inputs=list(inputs),
            timeout_s=timeout,memory_gib=memory))
    copper=args.copper_work
    solves={}
    for curvature in controls['curvature_safety']:
        solves[f'm{round(coarse_mesh*1e6)}-c{curvature:g}-p{round(base_port*100)}']=(coarse_mesh,curvature,base_port)
    solves[f'm{round(fine_mesh*1e6)}-c{args.basis_curvature:g}-p{round(base_port*100)}']=(fine_mesh,args.basis_curvature,base_port)
    solves[f'm{round(coarse_mesh*1e6)}-c{args.basis_curvature:g}-p{round(other_port*100)}']=(coarse_mesh,args.basis_curvature,other_port)
    for tag,(mesh,curvature,port) in solves.items():
        job('source-'+tag,['solve_linear_dc_study.py','--geometry-work',copper,'--matrix',args.matrix,'--work',w('source-'+tag),
            '--mesh',str(mesh),'--curvature-safety',str(curvature),'--port-fraction',str(port),'--max-dofs',str(args.max_dofs),'--threads','2'],
            inputs=[copper+'/summary.json',copper+'/copper.brep',args.matrix],timeout=args.source_timeout,memory=args.source_memory_gib)
        job('active-'+tag,['audit_finite_dc_winding_sections.py','--work',w('source-'+tag),'--output',w('active-'+tag)+'.json','--all-eligible','--threads','1'],
            ['source-'+tag],[w('source-'+tag)+'/summary.json'],timeout=3600.,memory=args.source_memory_gib)
    basis='source-'+f'm{round(coarse_mesh*1e6)}-c{args.basis_curvature:g}-p{round(base_port*100)}'
    passive=['audit_imported_dc_zero_sections.py','--work',w(basis),'--output',w('passive-basis')+'.json','--all-eligible-passive','--threads','1']
    if args.declared_no_stubs:passive.insert(-2,'--declared-no-stubs')
    job('passive-basis',passive,[basis],[w(basis)+'/summary.json'],timeout=3600.,memory=args.source_memory_gib)
    job('return-basis',['audit_finite_dc_sections.py','--work',w(basis),'--output',w('return-basis')+'.json','--threads','1'],[basis],[w(basis)+'/summary.json'],memory=args.source_memory_gib)
    job('primal-basis',['finite_copper_primal.py','--mesh-work',w(basis),'--work',w('primal-basis'),'--resistivity',str(args.resistivity),
        '--max-dofs','4000000','--threads','2'],[basis],[w(basis)+'/summary.json'],timeout=3600.,memory=args.source_memory_gib)
    job('rt0-basis',['export_rt0_current_source.py','--current-work',w(basis),'--work',w('rt0-basis')],[basis],[w(basis)+'/summary.json'],memory=args.source_memory_gib)
    spec=dict(schema='linear-dc-campaign-v1',name=args.prefix+'source-v1',scope=__doc__,cutoff_utc=args.cutoff,max_parallel=args.max_parallel,
        memory_budget_gib=args.memory_budget_gib,archive_root=str(ROOT),python=str(ROOT/'ngsolve-venv/bin/python'),matrix=args.matrix,
        basis=basis,jobs=jobs)
    with open(args.output,'x') as stream:stream.write(json.dumps(spec,indent=2)+'\n')
    print(len(jobs),'jobs; basis',basis)


if __name__=='__main__':main()
