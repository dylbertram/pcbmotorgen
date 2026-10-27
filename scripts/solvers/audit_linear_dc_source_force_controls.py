#!/usr/bin/env python3
"""Audit isolated current-source refinement through fresh nonlinear PM forces.

Checks mesh, drive-length and curvature sources at all sampled currents/poses
on an identical material quadrature and imported magnetic mesh. Re-verifies
source/local gates, saved unknowns, total and current-induced force differences
at the original 2% vector gate and 1e-8 N floor. Combined stationary force only;
no separate coil/shield body-force, general applicability or interpolation claim.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_dc_case_matrix import Evidence,validate_state_report
from audit_dc_section_refinement import compare_sections,load_sections
from audit_finite_dc_controls import MIXED,PRIMAL,load,resistance_check,validate_control
from audit_linear_dc_curvature import curvature_pair
from compare_finite_current_controls import compare
from post_project_force import sha
from source_snapshot import capture

POSES={'nominal':0.,'plus100um':.0001,'minus100um':-.0001}
PASSED='passed-linear-dc-source-refinement-force-controls-only'


def validate_plan(plan):
    if plan.get('schema')!='linear-dc-source-force-audit-plan-v1' or set(plan.get('variants',{}))!={'mesh','port','curvature'}:
        raise ValueError('All three isolated source axes required')
    if set(plan['baseline']['jobs'])!=set(POSES) or any(set(v['jobs'])!=set(POSES) for v in plan['variants'].values()):
        raise ValueError('All three explicit PM poses required for each source')


def same_layout(first,second):
    for key in ['points_m','element_numbers']:
        if not np.array_equal(first[key],second[key]):raise ValueError('Source refinement changed material quadrature layout')


def validate_source_force_summary(report,model,baseline_sha):
    if (report.get('status')!=PASSED or report.get('failures')!=[] or report.get('actual_model')!=model
        or report.get('baseline_source_sha256')!=baseline_sha or set(report.get('source_axes',[]))!={'mesh','port','curvature'}
        or report.get('magnetic_source_control_jobs')!=9 or report.get('saved_current_states')!=45 or report.get('comparison_pairs')!=9
        or report.get('relative_refinement_gate')!=.02 or report.get('force_vector_floor_n')!=1e-8):
        raise ValueError('Complete bound source-refinement force audit required')
    auxiliary=report.get('source_auxiliary_checks',{})
    if set(auxiliary)!={'passive','return','independent_h1','near_field','mesh_field','port_field','curvature_field'} or any(v.get('passed') is not True for v in auxiliary.values()):
        raise ValueError('Complete passive/return/independent/near-field source evidence required')
    expected={'0.0-total',*[str(i)+suffix for i in [.1,-.1,.5,-.5] for suffix in ['-total','-increment']]}
    for kind in ['mesh','port','curvature']:
        controls=report.get('controls',{}).get(kind,{})
        if not controls.get('resistance',{}).get('passed') or not controls.get('local_sections') or any(v.get('passed') is not True for v in controls['local_sections']):
            raise ValueError('Passing isolated current-source gates required')
        forces=controls.get('forces',{})
        if set(forces)!=set(POSES):raise ValueError('Missing sampled pose force controls')
        for pair in forces.values():
            if set(pair)!=expected or any(v.get('passed') is not True or not np.isfinite([v.get('difference_n',np.nan),v.get('limit_n',np.nan)]).all()
                or not 0<=v['difference_n']<=v['limit_n'] for v in pair.values()):raise ValueError('Incomplete or failed total/incremental force controls')


def verify_source_force_audit(evidence,path,model,baseline_sha):
    report=evidence.report(Path(path))
    validate_source_force_summary(report,model,baseline_sha)
    for name,digest in report['evidence_hashes'].items():
        if evidence.digest(name)!=digest:raise ValueError('Qualified source-refinement force evidence changed')
    return report


def source_auxiliary(e,root,plan,baseline,current,sections,model):
    from audit_linear_dc_near_field import probes
    requested=plan['source_evidence'];resolve=lambda name:(root/requested[name]).resolve();result={}
    for name,status in [('passive','passed-imported-passive-stub-zero-sections-only'),('return','passed-finite-dc-return-sections-only')]:
        report=e.report(resolve(name),'--output')
        if report['status']!=status or report['failures'] or report['source_work']!=str(baseline) or not report['sections'] or any(not v['passed'] for v in report['sections']):
            raise ValueError('Passing complete baseline '+name+' controls required')
        result[name]=dict(passed=True,report=str(resolve(name)))
    primal=load(resolve('independent_h1'),PRIMAL);bound=e.report(resolve('independent_h1')/'summary.json')
    if primal['source_mesh_work']!=str(baseline) or primal['input_summary_sha256']!=e.digest(baseline/'summary.json') or primal['mesh_sha256']!=current['mesh_sha256']:
        raise ValueError('Independent H1 reference belongs to another actual source')
    if e.digest(resolve('independent_h1')/'potential.sol')!=bound['potential_sha256']:raise ValueError('Independent H1 solution changed')
    agreement=resistance_check(current,primal,.05)
    if not agreement['passed']:raise ValueError('Independent H1 agreement failed')
    result['independent_h1']=dict(passed=True,check=agreement)
    near=e.report(resolve('near_field')/'summary.json')
    geometry_paths=[Path(p).with_name('summary.json') for p in current['input_hashes'] if p.endswith('/copper.brep')]
    if len(geometry_paths)!=1:raise ValueError('Unique actual copper required')
    geometry=e.report(geometry_paths[0]);expected_probes=probes(sections['sections'],geometry,model)
    if near['status']!='passed-sampled-linear-near-field-controls-only' or near['failures'] or near['probes']!=expected_probes or near['input_hashes'].get(str(baseline/'summary.json'))!=e.digest(baseline/'summary.json'):
        raise ValueError('Matching predetermined actual-region near-field controls required')
    for key,gate in [('volume_refinement',.02),('analytical_volume',.05),('opening_refinement',.02),('tree_analytical',.05)]:
        errors=np.asarray(near[key]['relative_errors'])
        if near[key]['limit']!=gate or len(errors)!=len(expected_probes) or not np.isfinite(errors).all() or min(errors)<0 or max(errors)>gate:
            raise ValueError('Near-field integration fails unchanged gates')
    result['near_field']=dict(passed=True,report=str(resolve('near_field')))
    for kind in ['mesh','port','curvature']:
        field=e.report(resolve(kind+'_field')/'summary.json')
        errors=field['field_relative_errors'] if kind=='curvature' else field['relative_errors']
        expected_status='passed-isolated-curvature-controls-only' if kind=='curvature' else 'passed-sampled-source-field-refinement-only'
        candidate=root/plan['variants'][kind]['current']
        if (field['status']!=expected_status or field['failures'] or field['probes']!=expected_probes
            or field['input_hashes'].get(str(candidate.resolve()/'summary.json'))!=e.digest(candidate/'summary.json')
            or len(errors)!=len(expected_probes) or not np.isfinite(errors).all() or min(errors)<0 or max(errors)>.02):
            raise ValueError('Matching fixed-probe source '+kind+' refinement required')
        result[kind+'_field']=dict(passed=True,report=str(resolve(kind+'_field')))
    return result


def coupling(evidence,work,pose):
    work=Path(work);report=evidence.report(work/'summary.json')
    validate_state_report(report,report['base_model'],'nonlinear',pose,'vector-b',1,8)
    for state in report['states'].values():
        if evidence.digest(work/state['solution'])!=state['solution_sha256']:raise ValueError('Saved coupled unknown changed')
    caches=[Path(p) for p in report['input_hashes'] if p.endswith('/material-current-source.npz')]
    if len(caches)!=1:raise ValueError('Exactly one actual source cache required')
    cache=evidence.report(caches[0].with_name('summary.json'))
    if evidence.digest(caches[0])!=cache['cache_sha256']:raise ValueError('Actual material-source cache changed')
    if cache['request']['degree']!=8:raise ValueError('Source control changed magnetic quadrature degree')
    return report,cache,caches[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root',type=Path,required=True);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    root=args.archive_root.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous source-force audits')
    plan=json.loads(args.plan.read_text());validate_plan(plan);e=Evidence();e.digest(args.plan)
    if plan.get('source_evidence_declaration'):e.digest(plan['source_evidence_declaration'])
    path=lambda value:(root/value).resolve()
    def source(variant):
        current_path=path(variant['current']);current=load(current_path,MIXED);bound=e.report(current_path/'summary.json')
        for name,key in [('mesh.vol','mesh_sha256'),('dc-current-potential.sol','solution_sha256')]:
            if e.digest(current_path/name)!=bound[key]:raise ValueError('Saved actual source artifact changed')
        sections_path=path(variant['active_sections']);sections,_=load_sections(sections_path,current_path);e.report(sections_path,'--output')
        return current,sections
    baseline=plan['baseline'];first,first_sections=source(baseline)
    mesh=path(baseline['magnetic_mesh']);mesh_report=e.report(mesh/'summary.json')
    if e.digest(mesh/'mesh.vol')!=mesh_report['mesh_sha256']:raise ValueError('Baseline magnetic mesh changed')
    baseline_reports={pose:coupling(e,path(value),POSES[pose]) for pose,value in baseline['jobs'].items()}
    auxiliary=source_auxiliary(e,root,plan,path(baseline['current']),first,first_sections,baseline_reports['nominal'][0]['base_model'])
    controls={};failures=[]
    for kind,variant in plan['variants'].items():
        second,second_sections=source(variant)
        coarse,fine=(0,1)
        if kind=='curvature':coarse,fine=curvature_pair(first,second)
        else:validate_control(first,second,kind)
        local=compare_sections([first_sections,second_sections][coarse],[first_sections,second_sections][fine])
        resistance=resistance_check([first,second][coarse],[first,second][fine],.02)
        if any(not x['passed'] for x in local) or not resistance['passed']:failures.append(kind+':source/local')
        variant_mesh=e.report(path(variant['mesh'])/'summary.json')
        if variant_mesh['input_hashes'].get(str(mesh/'mesh.vol'))!=mesh_report['mesh_sha256']:
            raise ValueError('Source control did not import the exact original magnetic mesh')
        for key in ['far','air_mesh','material_mesh','order','degree']:
            if variant_mesh['request'][key]!=mesh_report['request'][key]:raise ValueError('Source control changed magnetic discretization')
        poses={}
        for pose,value in variant['jobs'].items():
            actual,cache,archive=coupling(e,path(value),POSES[pose]);reference,reference_cache,reference_archive=baseline_reports[pose]
            if cache['source_work']!=str(path(variant['rt0'])):raise ValueError('Source control reused a different current basis')
            exported=e.report(path(variant['rt0'])/'summary.json')
            if exported['source_work']!=str(path(variant['current'])):raise ValueError('Source export is not bound to selected actual current')
            if actual['base_model']!=reference['base_model'] or actual['degree']!=reference['degree']:
                raise ValueError('Physical model or magnetic integration changed with source')
            with np.load(archive,allow_pickle=False) as a,np.load(reference_archive,allow_pickle=False) as b:same_layout(a,b)
            pair=compare([reference,actual][coarse],[reference,actual][fine],'refinement')
            if not all(x['passed'] for x in pair.values()):failures.append(kind+':'+pose)
            poses[pose]=pair
        controls[kind]=dict(resistance=resistance,local_sections=local,forces=poses,
            effective_loop_current_a=second['dc']['effective_loop_current_a'])
    e.unchanged();work.mkdir(parents=True)
    report=dict(status='failed-linear-dc-source-refinement-force-controls' if failures else PASSED,scope=__doc__,
        input_hashes={str(args.plan.resolve()):sha(args.plan)},evidence_hashes={str(p):h for p,h in e.hashes.items()},
        baseline_current_work=str(path(baseline['current'])),baseline_source_sha256=sha(path(baseline['current'])/'summary.json'),
        actual_model=baseline_reports['nominal'][0]['base_model'],source_axes=['mesh','port','curvature'],
        source_auxiliary_checks=auxiliary,
        magnetic_source_control_jobs=9,saved_current_states=45,comparison_pairs=9,controls=controls,failures=failures,
        relative_refinement_gate=.02,force_vector_floor_n=1e-8,
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['audit_dc_case_matrix.py','audit_dc_section_refinement.py','audit_finite_dc_controls.py','audit_linear_dc_curvature.py','compare_finite_current_controls.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    e.unchanged();(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(report['status'],failures,flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
