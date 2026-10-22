#!/usr/bin/env python3
"""Sampled near-copper and actual app-region affine RT0 integration controls.

Probe locations are fixed from physical geometry before evaluating fields.
Compare analytical cell-face integration with volume quadrature and tighter
tree openings at unchanged 2%/5% vector gates and a declared absolute floor.
Shared current exports are not an independent electrical solve. These probes
do not qualify all interior fields, arbitrary geometry or magnetic forces.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_finite_current_source_field import volume_field
from compare_reduced_fields import completed_receipt
from finite_current_tree import FiniteCurrentTree
from finite_tetra_current_field import tetrahedron_field
from post_project_force import sha
from source_snapshot import capture

FLOOR=1e-12


def probes(sections,geometry,model):
    traces=[s for s in sections if s['label'].startswith('trace:')]
    if not traces:raise ValueError('Eligible physical trace inventory required')
    lowest=min(s['centre_m'][2] for s in traces)
    eligible=sorted([s for s in traces if abs(s['centre_m'][2]-lowest)<1e-12],key=lambda s:s['label'])
    selected=[eligible[i] for i in np.unique(np.linspace(0,len(eligible)-1,min(3,len(eligible)),dtype=int))]
    layers=[layer for layer in geometry['geometry']['layers']
        if abs(layer['centre_z_m']+geometry['translation_m'][2]-lowest)<1e-12]
    if len(layers)!=1:raise ValueError('Unique actual lowest copper layer required')
    bottom=lowest-layers[0]['thickness_m']/2;result=[]
    for trace in selected:
        for gap in [25e-6,100e-6]:
            result.append(dict(label=f"near:{trace['label']}:{gap:g}",point_m=[*trace['centre_m'][:2],bottom-gap],
                role='near-copper-exterior',surface_gap_m=gap))
    for region in model['stack']+model['magnets']:
        low=np.asarray(region['origin_m']);size=np.asarray(region['size_m'])
        for fractions in [[.25,.5,.25],[.5,.5,.5],[.75,.5,.75]]:
            result.append(dict(label=region['name']+':'+','.join(map(str,fractions)),
                point_m=(low+size*np.asarray(fractions)).tolist(),role='actual-app-region-interior'))
    return result


def relative(a,b):
    return np.linalg.norm(a-b,axis=1)/np.maximum(np.linalg.norm(b,axis=1),FLOOR)


def validate_orders(orders):
    if len(orders)<2 or any(type(n) is not int or n not in [2,4,6,8,10,12] for n in orders) or any(a>=b for a,b in zip(orders,orders[1:])):
        raise ValueError('At least two strictly increasing supported volume quadrature orders required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['source-work','material-work','section-audit','work']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--orders',type=int,nargs='+',default=[4,6,10])
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    validate_orders(args.orders)
    if work.exists():parser.error('Preserve previous sampled field controls')
    material_path=args.material_work.resolve()/'summary.json';section_path=args.section_audit.resolve()
    source=json.loads((origin/'summary.json').read_text());material=json.loads(material_path.read_text());sections=json.loads(section_path.read_text())
    for report in [source,material,sections]:completed_receipt(report)
    if source['status']!='passed-affine-rt0-source-export-only' or material['status']!='completed-approved-disjoint-material-geometry-only' or material['failures']:
        raise ValueError('Accepted current export and disjoint model required')
    if sections['status']!='passed-finite-dc-all-eligible-winding-sections-only' or sections['failures'] or len(sections['sections'])!=sections['expected_sections']:
        raise ValueError('Whole passing all-eligible signed section audit required')
    current_path=Path(source['source_work'])/'summary.json';current=json.loads(current_path.read_text())
    if source['source_work']!=material['current_source_work'] or sections['source_work']!=source['source_work'] or sections['source_summary_sha256']!=sha(current_path):
        raise ValueError('Current/model/section provenance differs')
    geometry_paths=[Path(p).with_name('summary.json') for p in current['input_hashes'] if p.endswith('/copper.brep')]
    if len(geometry_paths)!=1:raise ValueError('Unique actual copper required')
    geometry_path=geometry_paths[0];geometry=json.loads(geometry_path.read_text())
    if sha(geometry_path)!=current['input_hashes'][str(geometry_path)]:raise ValueError('Physical copper summary changed')
    archive=origin/'rt0-source.npz'
    inputs={str(p):sha(p) for p in [origin/'summary.json',archive,material_path,section_path,current_path,geometry_path]}
    inputs.update(source['input_hashes']);inputs.update(material['input_hashes'])
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Bound source/model input changed')
    with np.load(archive,allow_pickle=False) as saved:
        cells=saved['vertices_m'][saved['cells']];mean=saved['mean_current_a_m2'];slope=saved['radial_slope_a_m3']
    selected=probes(sections['sections'],geometry,material['model']);points=np.asarray([p['point_m'] for p in selected])
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('Current quadrature engine changed')
    mesh_path=Path(source['source_work'])/'mesh.vol'
    if sha(mesh_path)!=source['input_hashes'][str(mesh_path)]:raise ValueError('Exact source mesh changed')
    mesh=ng.Mesh(str(mesh_path));located=mesh(points[:,0],points[:,1],points[:,2])
    if np.any(located['nr']>=0):raise ValueError('Probe intersects copper;no relocated or softened probe permitted')
    work.mkdir(parents=True);started=time.monotonic();loop=source['effective_loop_current_a']
    report=dict(status='running',scope=__doc__,input_hashes=inputs,probes=selected,field_floor_t_per_loop_a=FLOOR,
        effective_loop_current_a=loop,orders=args.orders,openings=[.075,.0375],levels={},failures=[],
        source_snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(n) for n in
            ['audit_finite_current_source_field.py','finite_tetra_current_field.py','finite_current_tree.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        exact=tetrahedron_field(points,cells,mean,radial_slope=slope)/loop
        report['analytical_field_t_per_loop_a']=exact.tolist();save()
        for order in report['orders']:
            now=time.monotonic();value=volume_field(points,cells,mean,slope,ng.IntegrationRule(ng.ET.TET,order))/loop
            report['levels'][str(order)]=dict(field_t_per_loop_a=value.tolist(),seconds=time.monotonic()-now);save()
            print('volume-order',order,report['levels'][str(order)]['seconds'],flush=True)
        tree=FiniteCurrentTree(cells,mean,slope,leaf_size=64);tree_fields=[]
        for opening in report['openings']:
            tree_fields.append(tree.field(points,opening)/loop)
            report['levels']['opening:'+str(opening)]=dict(field_t_per_loop_a=tree_fields[-1].tolist(),execution=tree.last_evaluation);save()
        middle,fine=[np.asarray(report['levels'][str(n)]['field_t_per_loop_a']) for n in report['orders'][-2:]]
        checks=dict(volume_refinement=(relative(middle,fine),.02),analytical_volume=(relative(exact,fine),.05),
            opening_refinement=(relative(*tree_fields),.02),tree_analytical=(relative(tree_fields[-1],exact),.05))
        for name,(errors,limit) in checks.items():
            report[name]=dict(relative_errors=errors.tolist(),limit=limit)
            if not np.isfinite(errors).all() or max(errors)>limit:report['failures'].append(name)
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Bound physical input changed during control')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Integration control implementation changed')
        report.update(status='failed-sampled-linear-near-field-controls' if report['failures'] else 'passed-sampled-linear-near-field-controls-only',seconds=time.monotonic()-started);save()
        if report['failures']:raise ValueError('Sampled source integration control failed')
    except BaseException as error:
        report.update(status='failed-sampled-linear-near-field-controls',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
