#!/usr/bin/env python3
"""Plan isolated source-refinement force controls on one fixed magnetic mesh.

Each already qualified mesh/port/curvature current basis gets a fresh material
binding, source cache, bare force, zero-current baselines and nonlinear solves
at all five currents and three poses. Only the exact original magnetic mesh is
reused, through the existing checked mesh-import path. No coupled unknowns or
forces are replayed. Stage 1 measures preflights before full caches are eligible.
"""
import argparse
import json
from pathlib import Path

from run_linear_dc_campaign import validate_campaign

POSES=[('nominal',0.),('plus100um',.0001),('minus100um',-.0001)]


def plan(spec,root,stage,cutoff):
    if spec.get('schema')!='linear-dc-source-force-controls-v1' or set(spec['variants'])!={'mesh','port','curvature'}:
        raise ValueError('Explicit mesh, port and curvature source controls required')
    if stage not in [1,2] or spec['currents_loop_a']!=[0.,.1,-.1,.5,-.5] or spec['linear_offsets_x_m']!=[0.,.0001,-.0001] or spec['relative_refinement_gate']!=.02 or spec['force_vector_floor_n']!=1e-8:
        raise ValueError('Original sampled states and unchanged force gates required')
    root=Path(root);jobs=[];audit=dict(schema='linear-dc-source-force-audit-plan-v1',baseline=spec['baseline'],variants={})
    mesh=root/spec['baseline']['magnetic_mesh'];copper=root/spec['copper_work']
    prefix=spec['prefix'];base=spec['magnetic_controls']
    if base!=dict(far=.06,air_mesh=.01,material_mesh=.0012,order=1,degree=8):
        raise ValueError('This plan requires the declared unchanged degree8 coarse magnetic discretization')
    for kind,variant in spec['variants'].items():
        w=lambda name:str(root/(prefix+kind+'-'+name+'-v1-20261022'))
        current=root/variant['current'];rt0=root/variant['rt0'];bare=w('bare')+'.json'
        def job(name,args,depends=(),inputs=(),timeout=300.):
            jobs.append(dict(name=kind+'-'+name,args=args,depends=[kind+'-'+d for d in depends],
                inputs=list(map(str,inputs)),timeout_s=timeout,memory_gib=1.3,log=Path(w(name)).name+'.log'))
        job('material',['prepare_linear_dc_material_model.py','--copper-work',str(copper),'--current-work',str(current),'--work',w('material')],
            inputs=[current/'summary.json',copper/'summary.json'])
        job('bare',['audit_finite_dc_pm_force.py','--work',str(current),'--output',bare,'--threads','1'],
            inputs=[current/'summary.json'],timeout=900)
        fixed=['--far',str(base['far']),'--air-mesh',str(base['air_mesh']),'--material-mesh',str(base['material_mesh']),
            '--order','1','--degree','8','--threads','1']
        job('mesh',['finite_current_zero_bias.py','--material-work',w('material'),'--source-work',str(rt0),'--mesh-work',str(mesh),
            '--work',w('mesh'),'--mesh-only',*fixed],['material'],[mesh/'summary.json',rt0/'summary.json'])
        job('cache-preflight',['cache_finite_current_material_source.py','--source-work',str(rt0),'--mesh-work',w('mesh'),
            '--work',w('cache-preflight'),'--preflight-only','--degree','8','--openings','0.15','0.075'],
            ['mesh'],[w('mesh')+'/summary.json'],300)
        job('pose-preflight',['finite_current_pose_force.py','--source-work',str(rt0),'--material-work',w('material'),
            '--bare-reference',bare,'--work',w('pose-preflight'),'--preflight-only'],['material','bare'],[bare],300)
        if stage==1:continue
        for job_entry in jobs:
            if job_entry['name'].startswith(kind+'-'):job_entry['prior']=True
        job('cache',['cache_finite_current_material_source.py','--source-work',str(rt0),'--mesh-work',w('mesh'),
            '--work',w('cache'),'--preflight-work',w('cache-preflight'),'--degree','8','--openings','0.15','0.075',
            '--max-cache-seconds','5400'],['cache-preflight'],[w('cache-preflight')+'/summary.json'],5700)
        job('poses',['finite_current_pose_force.py','--source-work',str(rt0),'--material-work',w('material'),
            '--bare-reference',bare,'--work',w('poses'),'--preflight-work',w('pose-preflight'),'--max-seconds','600'],
            ['pose-preflight'],[w('pose-preflight')+'/summary.json'],660)
        audit['variants'][kind]=dict(**variant,material=w('material'),mesh=w('mesh'),cache=w('cache'),bare=bare,poses=w('poses'),jobs={})
        for pose_name,pose in POSES:
            bias='bias-'+pose_name;coupling='coupling-'+pose_name
            job(bias,['finite_current_zero_bias.py','--material-work',w('material'),'--source-work',str(rt0),'--mesh-work',w('mesh'),
                '--work',w(bias),'--pm-offset-x',str(pose),*fixed],['mesh'],[w('mesh')+'/summary.json'],600)
            job(coupling,['finite_current_coupling.py','--cache-work',w('cache'),'--bias-work',w(bias),'--bare-force',bare,
                '--work',w(coupling),'--pose-reference-work',w('poses'),'--pm-offset-x',str(pose),'--threads','1'],
                ['cache','poses',bias],[w('cache')+'/summary.json',w(bias)+'/summary.json'],1200)
            audit['variants'][kind]['jobs'][pose_name]=w(coupling)
    campaign=dict(schema='linear-dc-campaign-v1',name=prefix+'stage'+str(stage),scope=__doc__,archive_root=str(root),
        python=str(root/'ngsolve-venv/bin/python'),cutoff_utc=cutoff,max_parallel=3,memory_budget_gib=4.,jobs=jobs)
    validate_campaign(campaign)
    return campaign,audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['declaration','archive-root','output','audit-plan']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--stage',type=int,choices=[1,2],required=True);parser.add_argument('--cutoff',required=True)
    args=parser.parse_args();spec=json.loads(args.declaration.read_text())
    campaign,audit=plan(spec,args.archive_root.resolve(),args.stage,args.cutoff)
    for job in campaign['jobs']:job['inputs'].append(str(args.declaration.resolve()))
    for path,value in [(args.output,campaign),(args.audit_plan,audit)]:
        with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
    print(len(campaign['jobs']),'jobs; stage',args.stage,flush=True)


if __name__=='__main__':main()
