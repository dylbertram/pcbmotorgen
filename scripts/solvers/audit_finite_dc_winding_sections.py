#!/usr/bin/env python3
"""Held-out signed trace/via sections against the saved DC resistor graph.

This compares two source formulations; it is not a magnetic or hardware check.
Finite pad/junction geometry is retained rather than tuned to the graph.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_finite_dc_controls import MIXED,load
from audit_finite_dc_sections import section,tetrahedra
from finite_copper_geometry import dimensions
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture
from winding_oracle import edge_points,resistances,unit_currents


def probes(fixture,shift,phase_data,all_eligible=False):
    spec=dimensions(fixture);traces=[];vias={};arcs=[]
    for network in fixture['networks']:
        sign=phase_data.get(network['net'],{}).get('current_a',0.)
        if not sign:continue
        shares,_=unit_currents(network,resistances(network,fixture['sim'],fixture['drive'],fixture['geometry_hints']))
        for index,(edge,share) in enumerate(zip(network['edges'],shares)):
            points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            if edge['geometry']['kind']=='via':
                normal=points[-1]-points[0];length=np.linalg.norm(normal)
                centre=(points[0]+points[-1])/2;key=tuple(centre)
                value=vias.setdefault(key,{'label':f"via:{network['net']}:{index}",'centre':centre,'normal':np.array([0.,0.,1.]),
                    'radius':spec['via_outer_radius_m']*1.2,'expected_per_loop_a':0.,'expected_area_m2':spec['via_barrel_area_m2']})
                value['expected_per_loop_a']+=sign*share*normal[2]/length
            else:
                if 'circular_arc_m' in edge['geometry']:
                    from finite_circular_copper import section_plane
                    layer=spec['layers'][edge['geometry']['layer']]
                    plane=section_plane(edge['geometry']['circular_arc_m'],layer['centre_z_m'],layer['trace_width_m'])
                    plane['centre']=(np.asarray(plane['centre'])+shift).tolist()
                    arcs.append(dict(plane,label=f"arc:{network['net']}:{index}",expected_per_loop_a=sign*share,
                        expected_area_m2=layer['trace_width_m']*layer['thickness_m']))
                    continue
                lengths=np.linalg.norm(np.diff(points,axis=0),axis=1);i=int(np.argmax(lengths));length=lengths[i]
                if length<.001:continue
                layer=spec['layers'][edge['geometry']['layer']]
                traces.append({'label':f"trace:{network['net']}:{index}",'centre':(points[i]+points[i+1])/2,
                    'normal':(points[i+1]-points[i])/length,'radius':layer['trace_width_m']*.75,
                    'expected_per_loop_a':sign*share,'expected_area_m2':layer['trace_width_m']*layer['thickness_m']})
    # Deterministic coverage across the exported order, not selected by FE error.
    result=[]
    for group,count in [(traces,6),(list(vias.values()),12)]:
        group=[p for p in group if abs(p['expected_per_loop_a'])>.05]
        if not group:raise ValueError('No eligible signed winding cross-sections')
        result.extend(group if all_eligible else [group[i] for i in np.unique(np.linspace(0,len(group)-1,min(count,len(group)),dtype=int))])
    result.extend(probe for probe in arcs if abs(probe['expected_per_loop_a'])>.05)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--all-eligible',action='store_true',help='Audit every eligible signed section instead of the historical6trace/12via sample')
    add_thread_option(parser);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous winding section audits')
    work=args.work.resolve();source=load(work,MIXED)
    if source['request']['geometry_order']!=1:raise ValueError('Need linear DC geometry')
    breps=[Path(p) for p in source['input_hashes'] if p.endswith('/copper.brep')]
    if len(breps)!=1:raise ValueError('Missing unique saved copper source')
    geometry_path=breps[0].with_name('summary.json')
    if sha(geometry_path)!=source['input_hashes'][str(geometry_path)]:raise ValueError('Saved geometry summary changed')
    geometry=json.loads(geometry_path.read_text());fixtures=[Path(p) for p in geometry['input_hashes'] if p.endswith('/fixture.json')]
    if len(fixtures)!=1 or sha(fixtures[0])!=geometry['input_hashes'][str(fixtures[0])]:raise ValueError('Saved winding fixture changed')
    returns=[Path(p) for p in source['input_hashes'] if p.endswith('/summary.json') and p!=str(geometry_path)]
    if len(returns)!=1 or sha(returns[0])!=source['input_hashes'][str(returns[0])]:raise ValueError('Closed source changed')
    closure=json.loads(returns[0].read_text())['closure'];fixture=json.loads(fixtures[0].read_text())
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('DC engine version differs')
    mesh=ng.Mesh(str(work/'mesh.vol'));space=ng.HDiv(mesh,order=0)*ng.L2(mesh,order=0)
    solution=ng.GridFunction(space);solution.Load(str(work/'dc-current-potential.sol'));tets=tetrahedra(mesh)
    records=[];failures=[];loop=source['dc']['effective_loop_current_a']
    selected=probes(fixture,np.asarray(geometry['translation_m']),closure['phase_data'],args.all_eligible)
    report={'status':'running','scope':__doc__,
        'source_work':str(work),'source_summary_sha256':sha(work/'summary.json'),'source_solution_sha256':source['solution_sha256'],
        'fixture_sha256':sha(fixtures[0]),'execution':runtime_metadata(),'sections':records,'failures':failures,
        'selection':'all eligible' if args.all_eligible else 'historical deterministic6trace/12via sample',
        'eligibility':'Active phases only; trace longest straight piece>=1mm; aggregate via currents; native circular midsections use exact tangent normals and a declared junction-clear window; absolute expected signed share>0.05. Excluded/near-zero/short/junction interior fields remain unqualified.',
        'expected_sections':len(selected),
        'source_snapshots':capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['audit_finite_dc_sections.py','winding_oracle.py','finite_circular_copper.py','finite_copper_geometry.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    for probe in selected:
        value=section(mesh,solution.components[0],tets,probe['centre'],probe['normal'],probe['radius'])
        actual=value['current_a']/loop;expected=probe['expected_per_loop_a']
        error=abs(actual-expected);limit=max(1e-8,.05*abs(expected))
        area_error=abs(value['area_m2']/probe['expected_area_m2']-1)
        value.update({'label':probe['label'],'current_per_loop_a':actual,'reference_per_loop_a':expected,
            'absolute_current_difference_per_loop_a':error,'current_limit_per_loop_a':limit,
            'relative_area_error':area_error,'passed':bool(error<=limit and area_error<=.02)})
        records.append(value)
        if not value['passed']:failures.append(probe['label'])
        if len(records)%10==0:
            save();print('sections',len(records),'/',len(selected),'failures',len(failures),flush=True)
    if sha(work/'summary.json')!=report['source_summary_sha256'] or sha(work/'dc-current-potential.sol')!=source['solution_sha256'] or sha(fixtures[0])!=report['fixture_sha256']:
        raise ValueError('Saved source changed during winding-section audit')
    for path,entry in report['source_snapshots'].items():
        if sha(Path(path))!=entry['sha256']:raise ValueError('Section audit implementation changed during execution')
    report['status']=('failed' if failures else 'passed')+('-finite-dc-all-eligible-winding-sections-only' if args.all_eligible else '-finite-dc-sampled-winding-sections-only')
    save()
    if failures:raise ValueError('Finite DC winding cross-section controls failed')


if __name__=='__main__':threaded_main(main)
