#!/usr/bin/env python3
"""Held-out passive-phase and full-via-stub zero-current sections.

These complement active winding sections, not replace them. Use the unchanged
2% area gate and declared 1e-8 A-per-loop zero-current floor. No force or generic
interior-field qualification follows from these isolated section checks.
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
from solver_threads import add_thread_option,threaded_main
from source_snapshot import capture
from winding_oracle import edge_points


def probes(fixture,geometry,phase_data,all_eligible=False):
    spec=dimensions(fixture);shift=np.asarray(geometry['translation_m']);passive=[];result=[];arcs=[]
    for network in fixture['networks']:
        if phase_data.get(network['net'],{}).get('current_a',0.):continue
        for index,edge in enumerate(network['edges']):
            points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            if edge['geometry']['kind']=='via':
                if all_eligible:
                    passive.append(dict(label=f"passive-via:{network['net']}:{index}",centre=points.mean(axis=0).tolist(),
                        normal=[0.,0.,1.],radius=spec['via_outer_radius_m']*1.2,expected_area_m2=spec['via_barrel_area_m2']))
                continue
            if 'circular_arc_m' in edge['geometry']:
                from finite_circular_copper import section_plane
                layer=spec['layers'][edge['geometry']['layer']]
                plane=section_plane(edge['geometry']['circular_arc_m'],layer['centre_z_m'],layer['trace_width_m'])
                plane['centre']=(np.asarray(plane['centre'])+shift).tolist()
                arcs.append(dict(plane,label=f"passive-arc:{network['net']}:{index}",
                    expected_area_m2=layer['trace_width_m']*layer['thickness_m']))
                continue
            lengths=np.linalg.norm(np.diff(points,axis=0),axis=1);i=int(np.argmax(lengths))
            if lengths[i]<.001:continue
            layer=spec['layers'][edge['geometry']['layer']]
            passive.append(dict(label=f"passive:{network['net']}:{index}",centre=((points[i]+points[i+1])/2).tolist(),
                normal=((points[i+1]-points[i])/lengths[i]).tolist(),radius=layer['trace_width_m']*.75,
                expected_area_m2=layer['trace_width_m']*layer['thickness_m']))
    if not passive:raise ValueError('No eligible undriven phase traces')
    result.extend(passive if all_eligible else [passive[i] for i in np.unique(np.linspace(0,len(passive)-1,min(6,len(passive)),dtype=int))])
    result.extend(arcs)
    for index,stub in enumerate(geometry['geometry']['full_physical_via_stubs']):
        raw=stub['full_centreplane_range_m'];landed=stub['electrical_landing_range_m']
        if landed is None:raise ValueError('No graph landing reference for full isolated via')
        for side,(lo,hi) in enumerate([(raw[0],landed[0]),(landed[1],raw[1])]):
            if hi<=lo:continue
            if hi-lo<=4*max(layer['thickness_m'] for layer in spec['layers']):
                raise ValueError('No isolated via stub section outside a pad/junction')
            result.append(dict(label=f'zero-stub:{index}:{side}',centre=[*stub['position_m'],(lo+hi)/2],
                normal=[0.,0.,1.],radius=spec['via_outer_radius_m']*1.2,expected_area_m2=spec['via_barrel_area_m2']))
    if not any(probe['label'].startswith('zero-stub:') for probe in result):
        raise ValueError('No actual full-via stub controls')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--all-eligible-passive',action='store_true',help='All undriven long-straight trace and barrel sections plus every physical stub; no FE-error-based selection')
    add_thread_option(parser);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve prior zero-current section audits')
    work=args.work.resolve();source=load(work,MIXED)
    copper=[Path(path) for path in source['input_hashes'] if path.endswith('/copper.brep')]
    if len(copper)!=1:raise ValueError('Unique actual imported geometry required')
    geometry_path=copper[0].with_name('summary.json');geometry=json.loads(geometry_path.read_text())
    fixture=[Path(path) for path in geometry['input_hashes'] if path.endswith('/fixture.json')]
    returns=[Path(path) for path in source['input_hashes'] if path.endswith('/summary.json') and path!=str(geometry_path)]
    if len(fixture)!=1 or len(returns)!=1:raise ValueError('Unique actual source/return inputs required')
    fixture=fixture[0]
    if sha(geometry_path)!=source['input_hashes'][str(geometry_path)] or sha(fixture)!=geometry['input_hashes'][str(fixture)] or sha(returns[0])!=source['input_hashes'][str(returns[0])]:
        raise ValueError('Imported source geometry/return changed')
    selected=probes(json.loads(fixture.read_text()),geometry,json.loads(returns[0].read_text())['closure']['phase_data'],args.all_eligible_passive)
    import ngsolve as ng
    if ng.__version__!=source['version'] or source['request']['geometry_order']!=1:raise ValueError('Changed or unsupported source discretization')
    mesh=ng.Mesh(str(work/'mesh.vol'));solution=ng.GridFunction(ng.HDiv(mesh,order=0)*ng.L2(mesh,order=0))
    solution.Load(str(work/'dc-current-potential.sol'));tets=tetrahedra(mesh)
    inputs={str(path):sha(path) for path in [work/'summary.json',work/'mesh.vol',work/'dc-current-potential.sol',fixture,geometry_path,returns[0]]}
    report=dict(status='running',scope=__doc__,source_work=str(work),input_hashes=inputs,sections=[],failures=[],
        selection='all eligible passive traces/vias, native arc midsections and all full stubs' if args.all_eligible_passive else 'six deterministic passive traces, native arc midsections and all full stubs',
        source_snapshots=capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['audit_finite_dc_sections.py','finite_copper_geometry.py','finite_circular_copper.py','winding_oracle.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    for probe in selected:
        value=section(mesh,solution.components[0],tets,probe['centre'],probe['normal'],probe['radius'])
        per_loop=value['current_a']/source['dc']['effective_loop_current_a'];area_error=abs(value['area_m2']/probe['expected_area_m2']-1)
        value.update(label=probe['label'],current_per_loop_a=per_loop,expected_per_loop_a=0.,current_floor_per_loop_a=1e-8,
                     relative_area_error=area_error,passed=bool(abs(per_loop)<=1e-8 and area_error<=.02))
        report['sections'].append(value)
        if not value['passed']:report['failures'].append(probe['label'])
        save()
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Imported DC zero-section input changed')
    for path,entry in report['source_snapshots'].items():
        if sha(Path(path))!=entry['sha256']:raise ValueError('Imported zero-section implementation changed')
    report['status']='failed' if report['failures'] else 'passed-imported-passive-stub-zero-sections-only';save()
    if report['failures']:raise ValueError('Imported passive/stub zero-current controls failed')


if __name__=='__main__':threaded_main(main)
