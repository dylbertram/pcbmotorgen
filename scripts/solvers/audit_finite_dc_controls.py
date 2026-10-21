#!/usr/bin/env python3
"""Isolated finite-copper DC resistance controls, not field/branch qualification."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from post_project_force import sha
from source_snapshot import capture


MIXED='completed-finite-copper-closed-dc-basis-unqualified'
PRIMAL='completed-independent-primal-dc-check-unqualified'


def validate_dc(report,status):
    if report.get('status')!=status:raise ValueError('DC job is incomplete or failed')
    dc=report['dc']
    keys=['relative_equation_residual','relative_power_balance','net_current_relative_error',
        'source_power_w','joule_power_w','effective_loop_resistance_ohm']
    values=np.array([dc[k] for k in keys],dtype=float)
    if not np.isfinite(values).all() or np.any(values<0):raise ValueError('Invalid DC checks')
    if any(dc[k]>limit for k,limit in zip(keys,[1e-9,1e-8,1e-9])):
        raise ValueError('DC original equation/current/power gate failed')
    if min(dc['source_power_w'],dc['joule_power_w'],dc['effective_loop_resistance_ohm'])<=0:
        raise ValueError('Nonpositive DC power/resistance')
    if abs(dc['joule_power_w']/dc['source_power_w']-1)>1e-8:
        raise ValueError('Reported DC power balance is inconsistent')
    if abs(dc['effective_loop_resistance_ohm']*dc['source_power_w']-1)>1e-8:
        raise ValueError('Not a unit-voltage DC basis')


def validate_control(first,second,kind):
    validate_dc(first,MIXED);validate_dc(second,MIXED)
    if first['version']!=second['version'] or first['input_hashes']!=second['input_hashes']:
        raise ValueError('DC control changed engine or saved physical inputs')
    controls=['mesh_m','port_fraction','geometry_order','iterative']
    changed={k for k in controls if first['request'][k]!=second['request'][k]}
    expected={'mesh':{'mesh_m'},'port':{'port_fraction'}}[kind]
    if changed!=expected:raise ValueError('DC refinement axes were not isolated')
    if first['request']['geometry_order']!=1:raise ValueError('Curved DC geometry remains unqualified')
    if kind=='mesh' and second['request']['mesh_m']>=first['request']['mesh_m']:
        raise ValueError('DC mesh was not refined')
    for key in ['volume_m3','solid_components','return_path_m','return_width_m','return_thickness_m']:
        if first['geometry'][key]!=second['geometry'][key]:raise ValueError('DC physical copper/return changed')
    if kind=='mesh' and first['geometry']['drive_path_m']!=second['geometry']['drive_path_m']:
        raise ValueError('DC port changed during mesh refinement')
    if kind=='mesh' and (first['mesh_sha256']==second['mesh_sha256'] or second['mesh_elements']<=first['mesh_elements']):
        raise ValueError('No independently finer DC mesh')
    for report in [first,second]:
        check=report['geometric_volume_check'];actual=abs(check['mesh_volume_m3']/report['geometry']['volume_m3']-1)
        if not np.isfinite(actual) or actual>.02:raise ValueError('DC mesh/CAD volume gate failed')


def resistance_check(first,second,tolerance):
    a=first['dc']['effective_loop_resistance_ohm'];b=second['dc']['effective_loop_resistance_ohm']
    error=abs(a/b-1)
    return {'first_resistance_ohm':a,'second_resistance_ohm':b,'relative_difference':error,
        'limit':tolerance,'passed':error<=tolerance}


def load(work,status):
    work=work.resolve()
    report=json.loads((work/'summary.json').read_text());validate_dc(report,status)
    if not report.get('command_receipt'):raise ValueError('Missing whole-job receipt')
    receipt=json.loads(Path(report['command_receipt']).read_text())
    if receipt.get('status')!='completed' or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0:
        raise ValueError('Whole DC job did not complete')
    if sha(work/'mesh.vol')!=report['mesh_sha256']:raise ValueError('DC mesh changed')
    for name,digest in report.get('input_hashes',{}).items():
        if sha(Path(name))!=digest:raise ValueError('DC saved physical input changed')
    if not report.get('source_snapshots'):raise ValueError('Missing archived DC implementation')
    for entry in report['source_snapshots'].values():
        path=(work/entry['snapshot']).resolve()
        if not path.is_relative_to(work) or sha(path)!=entry['sha256']:
            raise ValueError('Archived DC implementation changed')
    if status==MIXED:
        if sha(work/'dc-current-potential.sol')!=report['solution_sha256']:raise ValueError('DC solution changed')
        if sha(work/'closed-copper.brep')!=report['brep_sha256']:raise ValueError('DC copper CAD changed')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-work',type=Path,required=True);parser.add_argument('--second-work',type=Path,required=True)
    parser.add_argument('--kind',choices=['mesh','port','agreement'],required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();first=args.first_work.resolve();second=args.second_work.resolve()
    if args.output.exists():parser.error('Preserve previous DC controls')
    a=load(first,MIXED);b=load(second,PRIMAL if args.kind=='agreement' else MIXED)
    if args.kind=='agreement':
        if b['source_mesh_work']!=str(first) or b['input_summary_sha256']!=sha(first/'summary.json') or a['mesh_sha256']!=b['mesh_sha256']:
            raise ValueError('Primal check is not tied to the same mixed mesh/input summary')
    else:validate_control(a,b,args.kind)
    check=resistance_check(a,b,.05 if args.kind=='agreement' else .02)
    report={'status':('passed' if check['passed'] else 'failed')+'-finite-dc-'+args.kind+'-resistance-only',
        'scope':__doc__,'check':check,'source_summary_sha256':[sha(first/'summary.json'),sha(second/'summary.json')],
        'source_work':[str(first),str(second)],'source_snapshots':capture(args.output.parent,[Path(__file__)]),
        'remaining':['branch-current distribution','magnetic coupling','force/linkage/inductance','hardware validation']}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if not check['passed']:raise ValueError('Finite DC resistance control failed')


if __name__=='__main__':main()
