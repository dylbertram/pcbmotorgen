#!/usr/bin/env python3
"""Original-mesh unit-EMF drive-gauge control, not a source qualification.

The prescribed drive changes from 1/L to 6*s*(1-s)/L along the same straight
isolated port. Both line integrals are exactly one volt. Their difference is
the gradient of 3*s^2-2*s^3-s, zero at both port ends. Compatible HDiv current
should be invariant. No current normalization or physical geometry is fitted.
This does not replace drive-length, mesh/curvature, local or force controls.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from audit_finite_dc_controls import MIXED,load
from finite_copper_current import solve
from finite_copper_primal import saved_resistivity
from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def electric(ng,mesh,port):
    port=np.asarray(port,dtype=float)
    if port.shape!=(2,3) or not np.isfinite(port).all():raise ValueError('Explicit finite straight drive endpoints required')
    delta=port[1]-port[0];length=float(np.linalg.norm(delta))
    if length<=0:raise ValueError('Nonzero straight drive length required')
    unit=delta/length
    coordinate=ng.CoefficientFunction((ng.x-port[0,0],ng.y-port[0,1],ng.z-port[0,2]))
    s=ng.InnerProduct(coordinate,ng.CoefficientFunction(tuple(unit)))/length
    return mesh.MaterialCF({'drive':6*s*(1-s)*ng.CoefficientFunction(tuple(unit/length))},default=ng.CoefficientFunction((0,0,0)))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--max-dofs',type=int,default=8000000)
    add_thread_option(parser);args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous drive controls')
    source=load(origin,MIXED)
    if source['request']['geometry_order']!=1 or source['request'].get('drive_profile','uniform')!='uniform':
        raise ValueError('Original linear-geometry uniform-drive source required')
    brep=next(Path(path) for path in source['input_hashes'] if path.endswith('/copper.brep'))
    physical=json.loads(brep.with_name('summary.json').read_text());rho=physical['geometry']['copper_resistivity_ohm_m']
    geometry_path=saved_resistivity(source,rho)
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('Drive control engine changed')
    work.mkdir(parents=True);start=time.monotonic()
    paths=[origin/'summary.json',origin/'mesh.vol',origin/'dc-current-potential.sol',geometry_path]
    inputs={str(path):sha(path) for path in paths}
    report=dict(status='running',scope=__doc__,source_work=str(origin),input_hashes=inputs,version=ng.__version__,
        execution=runtime_metadata(),profile='6*s*(1-s)/L along the unchanged isolated drive port',
        exact_line_emf_v=1.,no_current_rescaling=True,
        source_snapshots=capture(work,[Path(__file__),Path(__file__).with_name('finite_copper_current.py'),
            Path(__file__).with_name('finite_copper_primal.py')]))
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        shutil.copy2(origin/'mesh.vol',work/'mesh.vol')
        if sha(work/'mesh.vol')!=source['mesh_sha256']:raise ValueError('Exact original mesh bytes changed during copy')
        mesh=ng.Mesh(str(work/'mesh.vol'));estimate=len(list(mesh.faces))+mesh.ne
        if estimate>args.max_dofs:raise ValueError('Drive-control resource cap exceeded before assembly')
        field=electric(ng,mesh,source['geometry']['drive_path_m'])
        solution,metadata=solve(ng,mesh,field,rho,True,work/'linear-progress.json','amg')
        solution.Save(str(work/'drive-profile-current.sol'))
        reference=ng.GridFunction(ng.HDiv(mesh,order=0)*ng.L2(mesh,order=0));reference.Load(str(origin/'dc-current-potential.sol'))
        delta=solution.components[0]-reference.components[0]
        baseline=float(ng.Integrate(rho*ng.InnerProduct(reference.components[0],reference.components[0]),mesh,order=6))
        difference=float(ng.Integrate(rho*ng.InnerProduct(delta,delta),mesh,order=6))
        relative=float(np.sqrt(max(difference,0.)/baseline))
        current_change=abs(metadata['source_power_w']/source['dc']['source_power_w']-1)
        if not np.isfinite([baseline,difference,relative,current_change]).all() or baseline<=0 or difference<0:
            raise ValueError('Invalid raw-current gauge comparison')
        report.update(dc=metadata,solution_sha256=sha(work/'drive-profile-current.sol'),
            current_control=dict(raw_rho_l2_current_relative_difference=relative,unit_emf_loop_current_relative_difference=current_change,
                                 limit=.02,passed=bool(relative<=.02 and current_change<=.02)))
        for path,digest in inputs.items():
            if sha(Path(path))!=digest:raise ValueError('Drive-control original input changed')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Drive-control implementation changed')
        if not report['current_control']['passed']:raise ValueError('Unit-EMF gauge/source control failed unchanged2%gate')
        report.update(status='passed-original-mesh-unit-emf-gauge-control-only',seconds=time.monotonic()-start);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-start);save();raise


if __name__=='__main__':threaded_main(main)
