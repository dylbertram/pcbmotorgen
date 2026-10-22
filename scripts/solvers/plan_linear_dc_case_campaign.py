#!/usr/bin/env python3
"""Emit the declared magnetic campaign for one qualified linear DC source case.

Mirrors the recorded 37-job coverage template (5 currents x nominal/+/-100um,
vector and scalar formulations, mesh/domain/quadrature/opening controls,
linear/vacuum limits) at the numerical values of the declared acceptance
matrix. Writes the campaign DAG and the matching aggregate-audit case plan.
No archived recorded force is reused.
"""
import argparse
import json
from pathlib import Path

ROOT=Path.home()/'.local/opt/solver-prototypes-macos'
POSES=[('nominal',0.),('plus100um',.0001),('minus100um',-.0001)]


def plan(prefix,copper,current,rt0,matrix,stage,cutoff,budgets,sections=None,expected_sections=None):
    base=matrix['magnetic_baseline'];control=matrix['isolated_magnetic_controls']
    mesh_levels={'coarse':dict(far=base['air_radius_m'],air=base['air_mesh_m'],material=base['material_mesh_m']),
        'refined':dict(far=base['air_radius_m'],air=base['air_mesh_m'],material=control['material_mesh_m']),
        'domain':dict(far=control['air_radius_m'],air=base['air_mesh_m'],material=base['material_mesh_m'])}
    w=lambda name:str(ROOT/(prefix+name+'-v1-20261022'))
    jobs=[]
    def job(name,args,depends=(),inputs=(),timeout=None,memory=None,kind='default'):
        jobs.append(dict(name=name,log=prefix+name+'-v1-20261022.log',args=args,depends=list(depends),inputs=list(inputs),
            timeout_s=timeout or budgets[kind]['timeout_s'],memory_gib=memory or budgets[kind]['memory_gib']))
    material=w('material');bare=str(ROOT/(prefix+'bare-pm-force-v1-20261022.json'))
    job('material',['prepare_linear_dc_material_model.py','--copper-work',copper,'--current-work',current,'--work',material],
        inputs=[current+'/summary.json'],kind='small')
    job('bare-force',['audit_finite_dc_pm_force.py','--work',current,'--output',bare,'--threads','2'],inputs=[current+'/summary.json'],kind='small')
    for level,m in mesh_levels.items():
        job('mesh-'+level,['finite_current_zero_bias.py','--material-work',material,'--source-work',rt0,'--work',w('mesh-'+level),'--mesh-only',
            '--far',str(m['far']),'--air-mesh',str(m['air']),'--material-mesh',str(m['material']),'--threads','2'],['material'],[material+'/summary.json'],kind='small')
    job('pose-preflight',['finite_current_pose_force.py','--source-work',rt0,'--material-work',material,'--bare-reference',bare,'--work',w('pose-preflight'),
        '--preflight-only'],['material','bare-force'],[material+'/summary.json',bare],kind='small')
    caches={'coarse':('coarse',8,[.15,base['source_opening']]),'refined':('refined',8,[.15,base['source_opening']]),
        'domain':('domain',8,[.15,base['source_opening']]),'opening':('coarse',8,[base['source_opening'],control['source_opening']]),
        'quadrature':('coarse',control['quadrature_degree'],[.15,base['source_opening']])}
    for name,(level,degree,openings) in caches.items():
        job('cache-preflight-'+name,['cache_finite_current_material_source.py','--source-work',rt0,'--mesh-work',w('mesh-'+level),'--work',w('cache-preflight-'+name),
            '--preflight-only','--degree',str(degree),'--openings',*map(str,openings)],['mesh-'+level],[w('mesh-'+level)+'/summary.json'],kind='small')
    audit=dict(case_prefix=prefix,material_work=material,source_work=rt0,quadrature_degree=control['quadrature_degree'],baseline_degree=8,
        quadrature_finer=control['quadrature_degree']>8,sections_report=sections,expected_sections=expected_sections,jobs={})
    if stage==1:return jobs,audit
    for entry in jobs:entry['prior']=True
    job('pose-forces',['finite_current_pose_force.py','--source-work',rt0,'--material-work',material,'--bare-reference',bare,'--work',w('pose-forces'),
        '--preflight-work',w('pose-preflight'),'--max-seconds',str(budgets['pose']['max_seconds'])],['pose-preflight'],[w('pose-preflight')+'/summary.json'],kind='pose')
    for name,(level,degree,openings) in caches.items():
        job('cache-'+name,['cache_finite_current_material_source.py','--source-work',rt0,'--mesh-work',w('mesh-'+level),'--work',w('cache-'+name),
            '--preflight-work',w('cache-preflight-'+name),'--degree',str(degree),'--openings',*map(str,openings),
            '--max-cache-seconds',str(budgets['cache']['max_cache_seconds'])],['cache-preflight-'+name],[w('cache-preflight-'+name)+'/summary.json'],kind='cache')
    m=mesh_levels
    for level in m:
        for pose_name,pose in POSES:
            for formulation,short in [('vector-b','vector'),('scalar-h','scalar')]:
                name=f'bias-{short}-{level}-{pose_name}'
                job(name,['finite_current_zero_bias.py','--material-work',material,'--source-work',rt0,'--work',w(name),'--mesh-work',w('mesh-'+level),
                    '--far',str(m[level]['far']),'--air-mesh',str(m[level]['air']),'--material-mesh',str(m[level]['material']),
                    '--formulation',formulation,'--pm-offset-x',str(pose),'--threads','2'],['mesh-'+level],[w('mesh-'+level)+'/summary.json'],kind='bias')
    def coupling(key,name,cache,bias,mode,formulation,order,pose,pose_name):
        args=['finite_current_coupling.py','--cache-work',w('cache-'+cache),'--bias-work',w(bias),'--bare-force',bare,'--threads','2','--mode',mode,'--work',w(name)]
        if formulation=='scalar-h':args+=['--formulation','scalar-h','--scalar-order',str(order)]
        elif order!=1:args+=['--vector-order',str(order)]
        depends=['cache-'+cache,bias]
        if pose:args+=['--pose-reference-work',w('pose-forces'),'--pm-offset-x',str(pose)];depends.append('pose-forces')
        job(name,args,depends,[w('cache-'+cache)+'/summary.json',w(bias)+'/summary.json'],kind='coupling')
        audit['jobs'][key]=dict(work=prefix+name+'-v1-20261022',mode=mode,pose=pose,formulation=formulation,order=order,
            degree=caches[cache][1])
    for pose_name,pose in POSES:
        for formulation,short,order in [('vector-b','vector',1),('scalar-h','scalar',2)]:
            for level in ['coarse','refined','domain','quadrature']:
                cache=level;mesh='coarse' if level=='quadrature' else level
                coupling(f'{pose_name}/{short}/{level}',f'nonlinear-{short}-{level}-{pose_name}',cache,f'bias-{short}-{mesh}-{pose_name}',
                    'nonlinear',formulation,order,pose,pose_name)
        coupling(f'{pose_name}/vector/opening',f'nonlinear-vector-opening-{pose_name}','opening',f'bias-vector-coarse-{pose_name}','nonlinear','vector-b',1,pose,pose_name)
    for formulation,short,order in [('vector-b','vector',matrix['isolated_magnetic_controls']['higher_order_limit_control']),('scalar-h','scalar',3)]:
        for level in ['coarse','refined','domain','quadrature']:
            mesh='coarse' if level=='quadrature' else level
            coupling(f'linear/{short}/{level}',f'linear-{short}-{level}',level,f'bias-{short}-{mesh}-nominal','linear',formulation,order,0.,'nominal')
    coupling('linear/vector/opening','linear-vector-opening','opening','bias-vector-coarse-nominal','linear','vector-b',
        matrix['isolated_magnetic_controls']['higher_order_limit_control'],0.,'nominal')
    coupling('vacuum','vacuum-vector','coarse','bias-vector-coarse-nominal','vacuum','vector-b',1,0.,'nominal')
    return jobs,audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['prefix','copper-work','current-work','rt0-work','matrix','output','audit-plan','cutoff','budgets','sections-report']:
        parser.add_argument('--'+key,required=key not in ['audit-plan','sections-report'])
    parser.add_argument('--expected-sections',type=int)
    parser.add_argument('--stage',type=int,choices=[1,2],required=True);parser.add_argument('--max-parallel',type=int,default=3)
    parser.add_argument('--memory-budget-gib',type=float,default=15.);args=parser.parse_args()
    matrix=json.loads(Path(args.matrix).read_text());budgets=json.loads(Path(args.budgets).read_text())
    jobs,audit=plan(args.prefix,args.copper_work,args.current_work,args.rt0_work,matrix,args.stage,args.cutoff,budgets,args.sections_report,args.expected_sections)
    spec=dict(schema='linear-dc-campaign-v1',name=args.prefix+'magnetic-stage'+str(args.stage),scope=__doc__,cutoff_utc=args.cutoff,
        max_parallel=args.max_parallel,memory_budget_gib=args.memory_budget_gib,archive_root=str(ROOT),python=str(ROOT/'ngsolve-venv/bin/python'),
        matrix=str(Path(args.matrix).resolve()),jobs=jobs)
    with open(args.output,'x') as stream:stream.write(json.dumps(spec,indent=2)+'\n')
    if args.audit_plan:
        with open(args.audit_plan,'x') as stream:stream.write(json.dumps(audit,indent=2)+'\n')
    print(len(jobs),'jobs',sum(1 for j in jobs if j['args'][0]=='finite_current_coupling.py'),'couplings')


if __name__=='__main__':main()
