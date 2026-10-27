#!/usr/bin/env python3
"""Bare finite-volume DC winding/PM interaction with independent force kernels.

Retains the saved copper, current distribution and explicit return. Excludes
ferrite, housing and current self-field. Does not qualify the source mesh or
inductance. Failed local geometry controls remain failed regardless of force
agreement. Current sources are streamed in bounded batches, without a fitted
wire radius or off-rule integration-point GridFunction evaluation.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_finite_dc_controls import MIXED,load
from pm_current_force import array_force
from post_project_force import sha
from reduced_potential import source_field
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def sources(ng,mesh,current,degree,batch_cells=2048):
    if degree not in [2,4,6] or batch_cells<1:raise ValueError('Invalid finite-current quadrature/resource controls')
    rule=ng.IntegrationRule(ng.ET.TET,degree)
    local=np.array([ip.point[:3] for ip in rule]);weights=np.array([ip.weight for ip in rule])
    corners=ng.IntegrationRule(points=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)],weights=[1.]*4)
    coordinate=ng.CoefficientFunction((ng.x,ng.y,ng.z));points=[];values=[];volumes=[]
    for element in mesh.Elements():
        if element.type!=ng.ET.TET:raise ValueError('Finite DC force requires tetrahedra')
        transform=mesh.GetTrafo(element);vertices=np.asarray(coordinate(transform(corners))).reshape(4,3)
        matrix=vertices[1:]-vertices[0];det=abs(float(np.linalg.det(matrix)))
        mapped=transform(rule);physical=np.asarray(coordinate(mapped)).reshape(-1,3)
        if det<=0 or np.max(abs(physical-(vertices[0]+local@matrix)))>1e-12:
            raise ValueError('Do not apply affine volume weights to curved current cells')
        value=np.asarray(current(mapped),dtype=float).reshape(-1,3)
        if not np.isfinite([physical,value]).all():raise ValueError('Invalid finite DC current sources')
        points.append(physical);values.append(value);volumes.append(weights*det)
        if len(points)==batch_cells:
            yield np.concatenate(points),np.concatenate(values),np.concatenate(volumes)
            points=[];values=[];volumes=[]
    if points:yield np.concatenate(points),np.concatenate(values),np.concatenate(volumes)


def model_summary(source,geometry_path):
    """Exactly one bound summary carrying the magnetic model, from inputs or declared study bindings."""
    bound=[*source['input_hashes'],*source.get('study_bindings',{})]
    candidates=[Path(p) for p in bound if p.endswith('/summary.json') and p!=str(geometry_path) and 'model' in json.loads(Path(p).read_text())]
    if len(candidates)!=1:raise ValueError('Exactly one bound magnetic model summary required')
    return candidates[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--body-orders',type=int,nargs='+',default=[2,4])
    add_thread_option(parser);args=parser.parse_args();work=args.work.resolve()
    if args.output.exists():parser.error('Preserve previous finite-current force audits')
    if len(args.body_orders)<2 or any(n not in [2,4,6] for n in args.body_orders) or any(a>=b for a,b in zip(args.body_orders,args.body_orders[1:])):
        parser.error('At least two strictly increasing supported quadrature orders required')
    source=load(work,MIXED)
    if source['request']['geometry_order']!=1:raise ValueError('Finite-current force requires linear source geometry')
    brep=next(Path(p) for p in source['input_hashes'] if p.endswith('/copper.brep'));geometry_path=brep.with_name('summary.json')
    geometry=json.loads(geometry_path.read_text());rho=geometry['geometry']['copper_resistivity_ohm_m']
    model_path=model_summary(source,geometry_path)
    model_source=json.loads(model_path.read_text());model=model_source['model'];magnets=model['magnets'];incident=source_field(model)
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('Finite-current force engine changed')
    mesh=ng.Mesh(str(work/'mesh.vol'));space=ng.HDiv(mesh,order=0)*ng.L2(mesh,order=0)
    solution=ng.GridFunction(space);solution.Load(str(work/'dc-current-potential.sol'));current=solution.components[0]
    output={'status':'running','scope':__doc__,'execution':runtime_metadata(),'source_work':str(work),
        'source_summary_sha256':sha(work/'summary.json'),'source_solution_sha256':source['solution_sha256'],
        'model_summary_sha256':sha(model_path),'levels':{},'failures':[],
        'source_snapshots':capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(p) for p in
            ['audit_finite_dc_controls.py','pm_current_force.py','reduced_potential.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for degree in args.body_orders:
            copper=np.zeros(3);pm=np.zeros((len(magnets),3));net=np.zeros(3);loss=0.;volume=0.;count=0
            for points,j,weights in sources(ng,mesh,current,degree):
                weighted=j*weights[:,None];copper+=np.cross(weighted,incident(points)).sum(axis=0)
                pm+=array_force(magnets,points,weighted);net+=weighted.sum(axis=0)
                loss+=rho*float(weights@np.sum(j*j,axis=1));volume+=float(weights.sum());count+=len(points)
            mover=pm.sum(axis=0);balance=float(np.linalg.norm(mover+copper))
            limit=max(1e-8,.02*float(np.linalg.norm(mover)))
            volume_error=abs(volume/source['geometric_volume_check']['mesh_volume_m3']-1)
            loss_error=abs(loss/source['dc']['joule_power_w']-1)
            moment=float(np.linalg.norm(net))/max(np.sqrt(loss/rho*volume),1e-300)
            passed=balance<=limit and volume_error<=1e-9 and loss_error<=1e-8 and moment<=1e-9
            output['levels'][str(degree)]={'points':count,'volume_m3':volume,'volume_relative_error':volume_error,
                'joule_power_w':loss,'joule_power_relative_error':loss_error,'net_current_relative_error':moment,
                'copper_source_force_n':copper.tolist(),'pm_array_force_n':mover.tolist(),'pm_individual_forces_n':pm.tolist(),
                'pm_force_n_per_loop_a':(mover/source['dc']['effective_loop_current_a']).tolist(),
                'action_reaction_error_n':balance,'action_reaction_limit_n':limit,'passed':bool(passed)}
            if not passed:output['failures'].append(f'quadrature{degree}: finite-current force/volume/power/current checks')
            save();print('quadrature',degree,'PM force',mover.tolist(),'balance',balance,flush=True)
        a=np.asarray(output['levels'][str(args.body_orders[-2])]['pm_array_force_n'])
        b=np.asarray(output['levels'][str(args.body_orders[-1])]['pm_array_force_n'])
        difference=float(np.linalg.norm(a-b));limit=max(1e-8,.02*float(np.linalg.norm(b)))
        output['quadrature_control']={'absolute_change_n':difference,'limit_n':limit,'passed':difference<=limit}
        if difference>limit:output['failures'].append('finite-current force quadrature refinement')
        actual=b/source['dc']['effective_loop_current_a']
        if 'direct_pm_current_force_n_per_a' in model_source:
            reference=np.asarray(model_source['direct_pm_current_force_n_per_a'])
            error=float(np.linalg.norm(actual-reference));limit=max(1e-8,.05*float(np.linalg.norm(reference)))
            output['filament_source_comparison']={'finite_pm_force_n_per_loop_a':actual.tolist(),'line_pm_force_n_per_loop_a':reference.tolist(),
                'absolute_change_n_per_a':error,'limit_n_per_a':limit,'passed':error<=limit,
                'scope':'Source-only finite versus filament interaction; does not qualify interior line fields or inductance.'}
            if error>limit:output['failures'].append('finite/filament bare PM interaction comparison')
        else:
            # Never invent a line reference for a model that did not record one.
            output['filament_source_comparison']={'available':False,'finite_pm_force_n_per_loop_a':actual.tolist(),
                'scope':'No recorded filament reference for this model; comparison not performed or claimed.'}
        if sha(work/'summary.json')!=output['source_summary_sha256'] or sha(work/'dc-current-potential.sol')!=source['solution_sha256'] or sha(model_path)!=output['model_summary_sha256']:
            raise ValueError('Finite-current source changed during force audit')
        for name,entry in output['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Force audit implementation changed')
        output['status']=('failed' if output['failures'] else 'passed')+'-bare-finite-dc-pm-force-only';save()
        if output['failures']:raise ValueError('Finite-current force audit failed')
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
