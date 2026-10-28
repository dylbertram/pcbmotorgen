#!/usr/bin/env python3
"""Independent primal DC check on the same immutable finite copper mesh.

Checks resistance/power/mean current. The H1-derived current is not substituted
for a compatible HDiv source in a gauge-sensitive magnetic solve.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from post_project_force import sha
from solver_threads import add_thread_option,threaded_main,runtime_metadata
from source_snapshot import capture


def saved_resistivity(source,requested):
    candidates=[Path(path) for path in source.get('input_hashes',{}) if path.endswith('/copper.brep')]
    if len(candidates)!=1:raise ValueError('Unique saved copper geometry required for independent resistivity binding')
    geometry_path=candidates[0].with_name('summary.json')
    if source['input_hashes'].get(str(geometry_path))!=sha(geometry_path):
        raise ValueError('Independent-current source geometry changed')
    geometry=json.loads(geometry_path.read_text())
    rho=geometry['geometry']['copper_resistivity_ohm_m']
    if not np.isfinite(rho) or rho<=0 or requested!=rho:
        raise ValueError('Independent current check must preserve the saved copper resistivity; no fitted value permitted')
    return geometry_path


def verify_potential_artifact(work,report):
    if not report.get('potential_sha256') or sha(Path(work)/'potential.sol')!=report['potential_sha256']:
        raise ValueError('Independent saved potential provenance is missing or changed')


def solve(ng,mesh,electric,resistivity,max_dofs=500000,order=2,max_corrections=3):
    if type(max_corrections) is not int or not 0<=max_corrections<=5:
        raise ValueError('Bounded original-matrix algebraic corrections required')
    # Quadratic geometry needs quadratic H1 to contain the physical coordinate
    # tests used by the global current-moment identity.
    space=ng.H1(mesh,order=order)
    if space.ndof>max_dofs:raise ValueError('Declared primal DC resource cap exceeded before matrix assembly')
    u,v=space.TnT();free=space.FreeDofs();free[0]=False
    rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,6)};dx=ng.dx(intrules=rules)
    matrix=ng.BilinearForm(space,symmetric=True);matrix+=ng.InnerProduct(ng.grad(u),ng.grad(v))*dx
    load=ng.LinearForm(space);load+=ng.InnerProduct(electric,ng.grad(v))*dx
    matrix.Assemble();load.Assemble();potential=ng.GridFunction(space)
    inverse=matrix.mat.Inverse(free,inverse='sparsecholesky')
    potential.vec.data=inverse*load.vec
    residual=load.vec.CreateVector();selected=np.array(free,dtype=bool)
    current=((electric-ng.grad(potential))/resistivity).Compile()
    volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6));passes=[]
    for iteration in range(max_corrections+1):
        residual.data=load.vec-matrix.mat*potential.vec
        relative=float(np.linalg.norm(residual.FV().NumPy()[selected]))/max(float(np.linalg.norm(load.vec.FV().NumPy()[selected])),1e-300)
        loss=float(ng.Integrate(resistivity*ng.InnerProduct(current,current),mesh,order=6));work=float(ng.Integrate(ng.InnerProduct(current,electric),mesh,order=6))
        net=np.asarray(ng.Integrate(current,mesh,order=6)).reshape(3)
        moment=float(np.linalg.norm(net))/max(np.sqrt(loss/resistivity*volume),1e-300)
        balance=abs(work/loss-1) if loss>0 else float('inf')
        passed=bool(np.isfinite([relative,loss,work,moment,balance]).all() and work>0 and loss>0
                    and relative<=1e-9 and balance<=1e-8 and moment<=1e-9)
        passes.append(dict(iteration=iteration,relative_equation_residual=relative,relative_power_balance=balance,
                           net_current_relative_error=moment,passed=passed))
        if passed or iteration==max_corrections:break
        # Correct the original assembled H1 equations with their existing exact
        # factorization. No resistivity, field, drive, geometry or gate is fitted.
        potential.vec.data+=inverse*residual
    metadata={'dofs':space.ndof,'relative_equation_residual':relative,'joule_power_w':loss,'source_power_w':work,
        'relative_power_balance':abs(work/loss-1) if loss>0 else None,'net_current_moment_a_m':net.tolist(),'net_current_relative_error':moment,
        'algebraic_refinement_passes':passes,'maximum_original_matrix_corrections':max_corrections,
        'scope':'Independent H1 DC resistance/power check only, not compatible magnetic source current'}
    return potential,metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mesh-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--resistivity',type=float,required=True);parser.add_argument('--max-dofs',type=int,default=500000)
    parser.add_argument('--algebraic-corrections',type=int,choices=range(6),default=3)
    add_thread_option(parser);args=parser.parse_args();origin=args.mesh_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve prior primal DC checks')
    source=json.loads((origin/'summary.json').read_text())
    if sha(origin/'mesh.vol')!=source['mesh_sha256']:raise ValueError('Primal-check mesh changed')
    receipt=json.loads(Path(source['command_receipt']).read_text())
    if receipt['status'] not in ['failed','completed']:raise ValueError('Primal-check source mesh is live/incomplete')
    if not np.isfinite(args.resistivity) or args.resistivity<=0:parser.error('Positive saved resistivity required')
    geometry_path=saved_resistivity(source,args.resistivity)
    input_hashes={str(path):sha(path) for path in [origin/'summary.json',origin/'mesh.vol',geometry_path]}
    import ngsolve as ng
    if ng.__version__!=source['version']:raise ValueError('Primal mesh engine version differs')
    work.mkdir(parents=True);started=time.monotonic();shutil.copy2(origin/'mesh.vol',work/'mesh.vol')
    report={'status':'running','scope':__doc__,'execution':runtime_metadata(),'mesh_sha256':source['mesh_sha256'],
        'input_summary_sha256':sha(origin/'summary.json'),'source_mesh_work':str(origin),'resistivity_ohm_m':args.resistivity,
        'input_hashes':input_hashes,
        'source_snapshots':capture(work,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        mesh=ng.Mesh(str(work/'mesh.vol'))
        port=source['geometry'].get('drive_path_m',source['geometry']['return_path_m'][1:3]);points=np.asarray(port);vector=points[1]-points[0];length=np.linalg.norm(vector)
        electric=mesh.MaterialCF({'drive':ng.CoefficientFunction(tuple(vector/length**2))},default=ng.CoefficientFunction((0.,0.,0.)))
        order=source['request'].get('geometry_order',2)
        potential,metadata=solve(ng,mesh,electric,args.resistivity,args.max_dofs,order,args.algebraic_corrections);report['dc']=metadata;report['potential_order']=order;save()
        if not np.isfinite([metadata['relative_equation_residual'],metadata['joule_power_w'],metadata['source_power_w'],metadata['net_current_relative_error']]).all() or metadata['relative_equation_residual']>1e-9 or metadata['joule_power_w']<=0 or metadata['relative_power_balance']>1e-8 or metadata['net_current_relative_error']>1e-9:
            raise ValueError('Primal DC equation/current/power check failed')
        report['dc']['effective_loop_resistance_ohm']=1/metadata['source_power_w'];potential.Save(str(work/'potential.sol'))
        report['potential_sha256']=sha(work/'potential.sol')
        verify_potential_artifact(work,report)
        for name,digest in input_hashes.items():
            if sha(Path(name))!=digest:raise ValueError('Independent-current physical inputs changed during solve')
        for name,entry in report['source_snapshots'].items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Independent-current implementation changed during solve')
        report.update(status='completed-independent-primal-dc-check-unqualified',seconds=time.monotonic()-started);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
