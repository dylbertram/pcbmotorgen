#!/usr/bin/env python3
"""Pre-assembly imported mesh area controls. Never evaluates an electric current.

Uses the existing deterministic active/passive/native-arc/stub section planes
and unchanged 2% area gate. A passing mesh-only audit is not source acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_finite_dc_controls import MIXED,load
from audit_finite_dc_sections import section,tetrahedra
from audit_finite_dc_winding_sections import probes as active_probes
from audit_imported_dc_zero_sections import probes as passive_probes
from finite_copper_curvature import validate_mesh_reuse
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main
from source_snapshot import capture


def area_check(area,expected):
    if not np.isfinite([area,expected]).all() or min(area,expected)<=0:
        raise ValueError('Positive finite measured and physical section areas required')
    relative=abs(area/expected-1.)
    return dict(relative_area_error=relative,expected_area_m2=expected,limit=.02,passed=bool(relative<=.02))


def checkpoint_inputs(work,source):
    work=Path(work).resolve();report=json.loads((work/'summary.json').read_text())
    validate_mesh_reuse(report,source,report['request']['curvature_safety'])
    receipt=json.loads(Path(report['command_receipt']).read_text())
    completed=report['status']=='completed-finite-copper-curvature-mesh-only'
    if completed:
        valid=receipt.get('status')=='completed' and type(receipt.get('exit_code')) is int and receipt['exit_code']==0
    else:
        valid=receipt.get('status')=='failed' and type(receipt.get('exit_code')) is int and receipt['exit_code']!=0
    if not valid:raise ValueError('Mesh checkpoint has no matching finished whole-job receipt')
    if any((work/name).exists() for name in ['dc-current-potential.sol','unaccepted-current-potential.sol']):
        raise ValueError('Mesh-only area audit must not import an electric field')
    if sha(work/'mesh.vol')!=report['mesh_sha256'] or sha(work/'closed-copper.brep')!=source['brep_sha256']:
        raise ValueError('Mesh checkpoint bytes changed')
    for path,digest in report['input_hashes'].items():
        if sha(Path(path))!=digest:raise ValueError('Mesh checkpoint physical inputs changed')
    if not report.get('source_snapshots'):raise ValueError('Mesh checkpoint lacks archived implementation')
    for entry in report['source_snapshots'].values():
        path=(work/entry['snapshot']).resolve()
        if not path.is_relative_to(work) or sha(path)!=entry['sha256']:
            raise ValueError('Mesh checkpoint archived implementation changed')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--mesh-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--all-eligible',action='store_true',help='All existing eligible active/passive section locations, not FE-error-selected')
    add_thread_option(parser);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous mesh-only area evidence')
    origin=args.source_work.resolve();work=args.mesh_work.resolve();source=load(origin,MIXED)
    checkpoint=checkpoint_inputs(work,source)
    geometry_path=next(Path(path).with_name('summary.json') for path in source['input_hashes'] if path.endswith('/copper.brep'))
    geometry=json.loads(geometry_path.read_text())
    fixture_path=next(Path(path) for path in geometry['input_hashes'] if path.endswith('/fixture.json'))
    if sha(fixture_path)!=geometry['input_hashes'][str(fixture_path)]:raise ValueError('Actual saved winding changed')
    return_paths=[Path(path) for path in source['input_hashes'] if path.endswith('/summary.json') and path!=str(geometry_path)]
    if len(return_paths)!=1:raise ValueError('Unique declared return required')
    fixture=json.loads(fixture_path.read_text());phase=json.loads(return_paths[0].read_text())['closure']['phase_data']
    selected=active_probes(fixture,np.asarray(geometry['translation_m']),phase,args.all_eligible)
    selected+=passive_probes(fixture,geometry,phase,args.all_eligible)
    import ngsolve as ng
    if ng.__version__!=checkpoint['version'] or checkpoint['request']['geometry_order']!=1:
        raise ValueError('Unsupported or changed mesh discretization')
    inputs={str(path):sha(path) for path in [origin/'summary.json',work/'summary.json',work/'mesh.vol',geometry_path,fixture_path,*return_paths]}
    report=dict(status='running',scope=__doc__,source_work=str(origin),mesh_work=str(work),input_hashes=inputs,
        expected_sections=len(selected),selection='all eligible' if args.all_eligible else 'historical deterministic sample',
        sections=[],failures=[],source_snapshots=capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(name) for name in
            ['audit_finite_dc_sections.py','audit_finite_dc_winding_sections.py','audit_imported_dc_zero_sections.py',
             'finite_copper_curvature.py','finite_circular_copper.py','finite_copper_geometry.py','winding_oracle.py']]]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    started=time.monotonic();save()
    try:
        mesh=ng.Mesh(str(work/'mesh.vol'));tets=tetrahedra(mesh);zero=ng.CoefficientFunction((0.,0.,0.))
        for probe in selected:
            value=section(mesh,zero,tets,probe['centre'],probe['normal'],probe['radius'])
            # A zero vector is only a geometric integration placeholder. Do not
            # emit a synthetic current as though it were a computed DC result.
            value.pop('current_a')
            value.update(label=probe['label'],**area_check(value['area_m2'],probe['expected_area_m2']))
            report['sections'].append(value)
            if not value['passed']:report['failures'].append(value['label'])
            if len(report['sections'])%10==0:
                save();print('area-sections',len(report['sections']),'/',len(selected),'failures',len(report['failures']),flush=True)
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Mesh-only area audit inputs changed')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Mesh-only area implementation changed')
        report.update(status=('failed' if report['failures'] else 'passed')+'-mesh-only-section-areas',seconds=time.monotonic()-started);save()
        if report['failures']:raise ValueError('Pre-assembly mesh section areas failed unchanged2%gate')
    except BaseException as error:
        report.update(status='failed-mesh-only-section-areas',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
