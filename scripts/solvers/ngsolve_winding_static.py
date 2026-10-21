#!/usr/bin/env python3
"""Nonlinear PM-biased static response to an explicitly closed saved winding.

Off-wire ideal DC filament sources, full-vector reversible ferrite law and an
explicit external return scenario. Reports independent mover force and only
the material contribution to differential line inductance. Copper self/skin
inductance, housing induction, core loss and actual cable CAD are not solved.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from audit_static_material_controls import load
from closed_winding import build
from closed_wire_source import coefficient
from compare_reduced_fields import completed_receipt
from ngsolve_material_motion import magnetic_form,translated_source
from pm_current_force import array_force,array_magnetization_force
from post_project_force import sha
from solver_threads import add_thread_option,runtime_metadata,threaded_main,positive_threads
from source_snapshot import capture
from tree_gauge import free_dofs
from vector_material import magnetization_b
from volume_field_quadrature import sample
from winding_coordinates import translation
from wire_material_contacts import contacts,material_inductance_resolved


def line_samples(segments,currents,n):
    fractions=(np.arange(n)+.5)/n;delta=segments[:,1]-segments[:,0]
    points=segments[:,0,None,:]+fractions[None,:,None]*delta[:,None,:]
    dl=currents[:,None,None]*delta[:,None,:]/n
    return points.reshape(-1,3),np.broadcast_to(dl,points.shape).reshape(-1,3)


def current_difference_entry(current,force_difference,material_difference,inductance_resolved):
    return {'current_step_a':current,'mover_kf_n_per_a':np.asarray(force_difference).tolist(),
        'unqualified_material_current_difference_h':float(material_difference),
        'material_differential_line_inductance_h':float(material_difference) if inductance_resolved else None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copper-work',type=Path,required=True);parser.add_argument('--bias-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--positive',default='A');parser.add_argument('--negative',default='B')
    parser.add_argument('--waypoint',nargs=3,type=float,action='append',required=True)
    parser.add_argument('--amplitudes',nargs=2,type=float,default=[.1,.05]);parser.add_argument('--green-workers',type=positive_threads,default=2)
    parser.add_argument('--cache-source',action='store_true',help='exact fixed wire values at the declared material quadrature, never a spatial interpolator')
    parser.add_argument('--pose-x',type=float,default=0.,help='PM translation only; copper, ferrite and return remain fixed')
    parser.add_argument('--bias-only',action='store_true',help='zero-current nonlinear bias/linkage for independent pose differences')
    add_thread_option(parser);args=parser.parse_args();work=args.work.resolve();copper=args.copper_work.resolve();bias=args.bias_work.resolve()
    if work.exists():parser.error('Preserve all winding-current trials')
    if not np.isfinite(args.amplitudes).all() or not args.amplitudes[0]>args.amplitudes[1]>0:parser.error('Two decreasing positive current steps required')
    if not np.isfinite(args.pose_x):parser.error('Finite PM pose offset required')
    base,_=load(bias);exported=json.loads((copper/'summary.json').read_text());completed_receipt(exported)
    if exported['status']!='passed-original-version-copper-export-only' or exported['failures']:raise ValueError('Unqualified saved-version copper')
    if base['model']['source_sha256']!=exported['source_project_sha256'] or base['model']['version_index']!=exported['version_index']:
        raise ValueError('Copper and ferrite bias use different source versions')
    audit=json.loads((copper/'free-space-copper-audit/summary.json').read_text())
    if sha(copper/'free-space-copper-audit/summary.json')!=exported['copper_audit_sha256']:raise ValueError('Copper audit changed')
    level=max(audit['levels'],key=int);fixture_path=copper/f'free-space-copper-audit/mesh-{level}/fixture.json'
    if sha(fixture_path)!=audit['levels'][level]['fixture_sha256']:raise ValueError('Copper fixture changed')
    fixture=json.loads(fixture_path.read_text());shift=translation(fixture['sim'],base['model'],exported['saved_mover_position_mm']*1e-3)
    segments,currents,closure=build(fixture,args.positive,args.negative,shift,args.waypoint)
    if np.max(segments[:,:,2])>=min(m['origin_m'][2] for m in base['model']['magnets']):
        raise ValueError('Current-to-PM face-kernel audit requires the entire explicit return below PM bottoms')
    solve_model=copy.deepcopy(base['model'])
    for magnet in solve_model['magnets']:magnet['origin_m'][0]+=args.pose_x
    solve_model['array_centre_mm'][0]+=args.pose_x*1e3
    source_contacts=contacts(segments,currents,solve_model);inductance_resolved=material_inductance_resolved(source_contacts)
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    work.mkdir(parents=True);shutil.copy2(bias/'mesh.vol',work/'mesh.vol')
    np.savez_compressed(work/'closed-wire-source.npz',segments_m=segments,current_per_line_amp=currents)
    output={'status':'running','scope':__doc__,'closure':closure,'translation_m':shift.tolist(),'version':ng.__version__,
        'model':solve_model,'source_pose_offset_m':[args.pose_x,0.,0.],'bias_only':args.bias_only,
        'execution':dict(runtime_metadata(),green_workers=args.green_workers),
        'mesh_sha256':sha(work/'mesh.vol'),'wire_source_sha256':sha(work/'closed-wire-source.npz'),
        'input_hashes':{str(p):sha(p) for p in [bias/'summary.json',bias/'initial-reaction.sol',copper/'summary.json',fixture_path]},
        'amplitudes_a':args.amplitudes,'cache_source_requested':args.cache_source,'states':{},'checks':{},'failures':[],
        'wire_material_contacts':source_contacts,
        'quantity_support':{'material_differential_inductance':'off-wire filament material increment only; spatial qualification pending' if inductance_resolved else
            'unresolved interface/interior filament; physical inductance suppressed',
            'total_differential_inductance':'not computed; finite copper self field/cross section missing',
            'mover_force_current_response':'experimental; mesh/return/operating-sweep qualification pending'},
        'source_snapshots':capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
            ['closed_winding.py','closed_wire_source.py','ngsolve_material_motion.py','vector_material.py','pm_current_force.py','winding_oracle.py','winding_coordinates.py','volume_field_quadrature.py','quadrature_source.py','wire_material_contacts.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json';started=time.monotonic()
    def save():path.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        mesh=ng.Mesh(str(work/'mesh.vol'));order=base['request']['order'];degree=2*(order+1)+base['request']['bonus_order']
        space=ng.HCurl(mesh,order=order,nograds=True,dirichlet='outer');selected,_=free_dofs(ng,mesh,space,space);free=np.array(selected,dtype=bool)
        state=ng.GridFunction(space);initial=ng.GridFunction(space);initial.Load(str(bias/'initial-reaction.sol'))
        position=[ng.Parameter(0.) for _ in range(3)];pm=translated_source(ng,solve_model,position);pm_gradients=[pm.Diff(p).Compile() for p in position]
        bunit,_=coefficient(ng,segments,currents);amplitude=ng.Parameter(0.);source=(pm+amplitude*bunit).Compile()
        rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,degree)}
        form_source=source
        if args.cache_source:
            from quadrature_source import fixed_source
            regions='|'.join(m['name'] for m in base['model']['stack'] if m['mu_r']>1 and m['name']!='housing')
            cached,source_storage,rules,metadata=fixed_source(ng,mesh,bunit,regions,degree)
            # Only the nonlinear energy/gradient/tangent uses these exact rule
            # values. All below observables/force quadrature keep analytic B.
            form_source=(pm+amplitude*cached).Compile()
            np.savez_compressed(work/'wire-source-quadrature.npz',**{f'component_{i}':np.array(g.vec.FV().NumPy()) for i,g in enumerate(source_storage)})
            output['fixed_source_cache']=dict(metadata,archive='wire-source-quadrature.npz',sha256=sha(work/'wire-source-quadrature.npz'));save()
        form=magnetic_form(ng,space,mesh,base['model'],ng.CacheCF(form_source),rules);residual=state.vec.CreateVector()
        moments=[]
        for material in base['model']['stack']:
            if material['mu_r']<=1 or material['name']=='housing':continue
            moment=magnetization_b(ng,source+ng.curl(state),material['mu_r'],material['bsat_t']).Compile()
            observable=ng.CoefficientFunction(tuple([ng.InnerProduct(moment,bunit)]+[-ng.InnerProduct(moment,g) for g in pm_gradients])).Compile()
            moments.append((material['name'],moment,observable))
        direct=[]
        for subdivisions in [10,20]:
            points,dl=line_samples(segments,currents,subdivisions)
            direct.append(array_force(solve_model['magnets'],points,dl,args.green_workers).sum(axis=0))
        direct_change=float(np.linalg.norm(direct[1]-direct[0]));direct_limit=max(1e-8,.02*float(np.linalg.norm(direct[1])))
        output['direct_pm_current_force_n_per_a']=direct[1].tolist()
        output['checks']['wire_pm_force_quadrature']={'change_n_per_a':direct_change,'limit_n_per_a':direct_limit,'passed':direct_change<=direct_limit}
        if direct_change>direct_limit:raise ValueError('Wire-to-PM force integration did not converge')
        for current in ([0.] if args.bias_only else [0.,args.amplitudes[0],-args.amplitudes[0],args.amplitudes[1],-args.amplitudes[1]]):
            amplitude.Set(current);state.vec[:]=0.;form.Apply(state.vec,residual);scale=float(np.linalg.norm(residual.FV().NumPy()[free]))
            state.vec.data=initial.vec
            result=NewtonMinimization(form,state,freedofs=selected,maxit=60,maxerr=1e-12,inverse='sparsecholesky',linesearch=True,printing=True)
            form.Apply(state.vec,residual);relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/max(scale,1e-30)
            if result[0]!=0 or relative>1e-9:raise ValueError('Nonlinear winding equilibrium did not converge')
            values=np.zeros(4)
            for region,_,observable in moments:
                values+=np.asarray(ng.Integrate(observable,mesh,definedon=mesh.Materials(region),order=degree)).reshape(4)
            linkage=values[0];source_force=values[1:];energy=float(form.Energy(state.vec));delta=1e-4
            amplitude.Set(current+delta);above=float(form.Energy(state.vec));amplitude.Set(current-delta);below=float(form.Energy(state.vec));amplitude.Set(current)
            derivative=(above-below)/(2*delta);derivative_error=abs(derivative+linkage)
            if derivative_error>max(1e-12,1e-5*abs(linkage)):raise ValueError('Material linkage does not match the partial source-energy derivative')
            material_force=[]
            for quadrature,increment in [(8,1e-7),(10,5e-8)]:
                material_pm=np.zeros(3)
                for region,moment,_ in moments:
                    points,m,weights=sample(ng,mesh,moment,region,quadrature)
                    material_pm+=array_magnetization_force(solve_model['magnets'],points,m*weights[:,None],increment,args.green_workers).sum(axis=0)
                material_force.append(material_pm)
            imbalance=float(np.linalg.norm(material_force[-1]+source_force));limit=max(1e-8,.02*float(np.linalg.norm(source_force)))
            refinement=float(np.linalg.norm(material_force[-1]-material_force[0]))
            if max(imbalance,refinement)>limit:raise ValueError('Independent current-biased material PM force failed')
            mover=material_force[-1]+current*direct[-1];filename=f'current-{current:+.6f}.sol';state.Save(str(work/filename))
            output['states'][str(current)]={'relative_residual':relative,'newton_result':list(result),'reduced_energy_j':energy,
                'material_linkage_wb':float(linkage),'material_linkage_energy_derivative_error_wb':derivative_error,
                'material_source_force_n':source_force.tolist(),'independent_material_pm_force_n':material_force[-1].tolist(),
                'material_force_balance_error_n':imbalance,'material_force_refinement_n':refinement,'force_limit_n':limit,
                'pm_array_force_n':mover.tolist(),'solution':filename,'solution_sha256':sha(work/filename)}
            save();print('current',current,'PM force',mover.tolist(),'material linkage',linkage,flush=True)
        differences=[]
        for current in ([] if args.bias_only else args.amplitudes):
            positive=output['states'][str(current)];negative=output['states'][str(-current)]
            differences.append(current_difference_entry(current,(np.array(positive['pm_array_force_n'])-negative['pm_array_force_n'])/(2*current),
                (positive['material_linkage_wb']-negative['material_linkage_wb'])/(2*current),inductance_resolved))
        output['current_differences']=differences
        if not args.bias_only:
            coarse,fine=differences;kf=np.array(fine['mover_kf_n_per_a']);kf_change=float(np.linalg.norm(kf-coarse['mover_kf_n_per_a']))
            inductance=fine['unqualified_material_current_difference_h'];l_change=abs(inductance-coarse['unqualified_material_current_difference_h'])
            output['checks']['current_difference_refinement']={'kf_change_n_per_a':kf_change,'kf_limit_n_per_a':max(1e-8,.02*float(np.linalg.norm(kf))),
                'material_inductance_change_h':l_change,'material_inductance_limit_h':max(1e-12,.02*abs(inductance))}
            if kf_change>output['checks']['current_difference_refinement']['kf_limit_n_per_a'] or l_change>output['checks']['current_difference_refinement']['material_inductance_limit_h']:
                raise ValueError('Differential current response did not converge under current-step refinement')
        for p,digest in output['input_hashes'].items():
            if sha(Path(p))!=digest:raise ValueError('Winding-current input changed')
        for p,entry in output['source_snapshots'].items():
            if sha(Path(p))!=entry['sha256']:raise ValueError('Winding-current implementation changed')
        output.update(status='completed-closed-winding-nonlinear-bias-linkage-unqualified' if args.bias_only else 'completed-closed-winding-nonlinear-current-response-unqualified',seconds=time.monotonic()-started);save()
    except BaseException as error:
        output.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
