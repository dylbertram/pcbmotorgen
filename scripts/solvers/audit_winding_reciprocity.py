#!/usr/bin/env python3
"""Mover Kf versus independent PM-position derivative of circuit linkage.

Requires completed nonlinear current/pose jobs with fixed copper/return/mesh.
Linkage includes reciprocal free-space PM coupling and nonlinear material
magnetization, not copper self inductance. Passing is only x reciprocity at
one explicit return scenario/mesh, not spatial or hardware qualification.
"""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture
from wire_pm_linkage import linkage


def load(work):
    report=json.loads((work/'summary.json').read_text());completed_receipt(report)
    if report['status'] not in ['completed-closed-winding-nonlinear-current-response-unqualified','completed-closed-winding-nonlinear-bias-linkage-unqualified'] or report['failures']:
        raise ValueError('Need complete nonlinear winding jobs, not partial states')
    for file,key in [('mesh.vol','mesh_sha256'),('closed-wire-source.npz','wire_source_sha256')]:
        if sha(work/file)!=report[key]:raise ValueError('Winding input archive changed')
    for state in report['states'].values():
        if state['relative_residual']>1e-9 or sha(work/state['solution'])!=state['solution_sha256']:
            raise ValueError('Unconverged or changed winding field')
    cache=report['fixed_source_cache']
    if cache['relative_source_l2_error']>1e-13 or sha(work/cache['archive'])!=cache['sha256']:raise ValueError('Changed exact source cache')
    for entry in report['source_snapshots'].values():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Changed archived winding physics')
    return report


def pose_model(base,candidate,offset):
    expected=copy.deepcopy(base['model'])
    for magnet in expected['magnets']:magnet['origin_m'][0]+=offset
    expected['array_centre_mm'][0]+=offset*1e3
    if candidate['model']!=expected or candidate['source_pose_offset_m']!=[offset,0.,0.]:raise ValueError('Pose trial changed physical model beyond PM translation')
    for key in ['translation_m','closure','mesh_sha256']:
        if candidate[key]!=base[key]:raise ValueError('Pose derivative moved copper/return or changed mesh')
    physics=['closed_wire_source.py','vector_material.py','pm_current_force.py','quadrature_source.py','ngsolve_material_motion.py']
    for name in physics:
        first=next(v['sha256'] for k,v in base['source_snapshots'].items() if Path(k).name==name)
        second=next(v['sha256'] for k,v in candidate['source_snapshots'].items() if Path(k).name==name)
        if first!=second:raise ValueError('Pose/current constitutive or source definitions differ')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['current-work','plus-coarse','minus-coarse','plus-fine','minus-fine','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--degrees',nargs=2,type=int,default=[12,18]);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous winding reciprocity audits')
    if not 2<=args.degrees[0]<args.degrees[1]<=64:parser.error('Two increasing PM volume quadrature degrees required')
    current=load(args.current_work)
    if current.get('source_pose_offset_m',[0.,0.,0.])!=[0.,0.,0.] or len(current['current_differences'])!=2:raise ValueError('Need centred current-difference baseline')
    paths={k:getattr(args,k.replace('-','_')) for k in ['plus-coarse','minus-coarse','plus-fine','minus-fine']}
    records={k:load(p) for k,p in paths.items()};coarse=records['plus-coarse']['source_pose_offset_m'][0];fine=records['plus-fine']['source_pose_offset_m'][0]
    if not coarse>fine>0:raise ValueError('Two decreasing positive PM pose steps required')
    with np.load(args.current_work/'closed-wire-source.npz',allow_pickle=False) as wire:
        segments=np.array(wire['segments_m']);currents=np.array(wire['current_per_line_amp'])
    output={'status':'running','scope':__doc__,'levels':{},'checks':{},'failures':[],
        'input_hashes':{str(p/'summary.json'):sha(p/'summary.json') for p in [args.current_work,*paths.values()]},
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('wire_pm_linkage.py'),Path(__file__).with_name('closed_wire_source.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for label,record in records.items():
            delta=coarse if label.endswith('coarse') else fine;offset=delta if label.startswith('plus') else -delta
            pose_model(current,record,offset)
            with np.load(paths[label]/'closed-wire-source.npz',allow_pickle=False) as wire:
                if not np.array_equal(segments,wire['segments_m']) or not np.array_equal(currents,wire['current_per_line_amp']):
                    raise ValueError('Pose changed the physical signed winding source')
            material=record['states']['0.0']['material_linkage_wb'];values={}
            for degree in args.degrees:
                free=linkage(record['model']['magnets'],segments,currents,degree)
                values[str(degree)]={'free_space_pm_linkage_wb':free,'material_linkage_wb':material,'total_pm_bias_linkage_wb':free+material}
            output['levels'][label]=values;save()
        derivatives={}
        for label,step in [('coarse',coarse),('fine',fine)]:
            derivatives[label]={str(degree):(output['levels']['plus-'+label][str(degree)]['total_pm_bias_linkage_wb']-
                output['levels']['minus-'+label][str(degree)]['total_pm_bias_linkage_wb'])/(2*step) for degree in args.degrees}
        output['pose_linkage_derivative_n_per_a']=derivatives
        kf=float(current['current_differences'][-1]['mover_kf_n_per_a'][0]);answer=derivatives['fine'][str(args.degrees[-1])]
        limit=max(1e-8,.02*max(abs(kf),abs(answer)))
        for name,error in [('current_vs_linkage',abs(kf-answer)),('position_difference_refinement',abs(derivatives['coarse'][str(args.degrees[-1])]-answer)),
            ('pm_volume_quadrature_refinement',abs(derivatives['fine'][str(args.degrees[0])]-answer))]:
            output['checks'][name]={'absolute_change_n_per_a':error,'limit_n_per_a':limit,'passed':error<=limit}
            if error>limit:output['failures'].append(name)
        output['independent_current_force_derivative_x_n_per_a']=kf
        for p,digest in output['input_hashes'].items():
            if sha(Path(p))!=digest:raise ValueError('Nonlinear reciprocity input changed')
        for p,entry in output['source_snapshots'].items():
            if sha(Path(p))!=entry['sha256']:raise ValueError('Reciprocity implementation changed')
        output['status']='failed' if output['failures'] else 'passed-x-mover-force-flux-linkage-reciprocity-one-mesh-only';save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
