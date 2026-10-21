#!/usr/bin/env python3
"""Static nonlinear reaction-A solve for the archived finite PM/material model.

Independent B-energy formulation for comparison with the qualified H-potential
response. Analytical PM particular field is shared/disclosed. HCurl reaction A
uses an exact tree gauge, no penalty mass. No conductivity, winding or motion.
Quarter-domain tangential-A parity is valid only for the centred symmetric case.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from ngsolve_reduced import source_coefficient
from post_project_force import sha
from post_reduced_force import case_field
from reduced_inputs import validate_reduced_inputs
from reduced_potential import source_field
from solver_threads import add_thread_option,runtime_metadata,threaded_main
from source_snapshot import capture
from tree_gauge import free_dofs
from vector_material import reduced_density,magnetization_b,MU0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--order',type=int,choices=[0,1,2],default=2)
    parser.add_argument('--bonus-order',type=int,default=4);add_thread_option(parser)
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous vector-material trials')
    if not 0<=args.bonus_order<=12:parser.error('Quadrature bonus must be in [0,12]')
    source=json.loads((origin/'summary.json').read_text());case_field(origin,source,'bare');solver=validate_reduced_inputs(origin,source)
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    from netgen.read_gmsh import ReadGmsh
    work.mkdir(parents=True);shutil.copy2(origin/'project.msh',work/'project.msh')
    snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
        ['vector_material.py','ngsolve_reduced.py','tree_gauge.py','solver_threads.py','reduced_inputs.py']]])
    report={'status':'running','scope':__doc__,'backend':'NGSolve-vector-reaction-A','version':ng.__version__,
        'execution':runtime_metadata(),'model':source['model'],'solver_geometry_model':solver,
        'quarter_symmetry':source['quarter_symmetry'],'source_summary_sha256':sha(origin/'summary.json'),
        'mesh_sha256':sha(work/'project.msh'),'order':args.order,'bonus_order':args.bonus_order,
        'source_snapshots':snapshots,'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();started=time.monotonic()
    try:
        mesh=ng.Mesh(ReadGmsh(str(work/'project.msh')))
        boundary='outer|symmetry_x|symmetry_y' if source['quarter_symmetry'] else 'outer'
        fes=ng.HCurl(mesh,order=args.order,nograds=True,dirichlet=boundary)
        selected,tree_count=free_dofs(ng,mesh,fes,fes)
        free=np.array(selected,dtype=bool);reaction=ng.GridFunction(fes);trial=fes.TrialFunction()
        bsource=source_coefficient(ng,source['model']).Compile();fixed=ng.CacheCF(bsource)
        rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,2*(args.order+1)+args.bonus_order)}
        measure=lambda name:ng.dx(definedon=mesh.Materials(name),intrules=rules)
        form=ng.BilinearForm(fes,symmetric=True)
        magnetic_names=[]
        for layer in solver['stack']:
            magnetic_names.append(layer['name'])
            density=reduced_density(ng,ng.curl(trial),fixed,layer['mu_r'],layer['bsat_t']).Compile()
            form+=ng.Variation(density*measure(layer['name']))
        other=[name for name in mesh.GetMaterials() if name not in magnetic_names]
        if other:form+=ng.Variation((ng.InnerProduct(ng.curl(trial),ng.curl(trial))/(2*MU0))*measure('|'.join(other)))
        table=np.loadtxt(origin/'bare/source.txt');points=table[:,:3]
        computed=np.asarray(bsource(mesh(points[:,0],points[:,1],points[:,2]))).reshape(-1,3)
        error=float(np.max(abs(computed-source_field(source['model'])(points))))
        report.update(source_coefficient_error_t=error,dofs=fes.ndof,free_dofs=int(free.sum()),tree_fixed_edges=tree_count,
            tangential_dirichlet=boundary)
        if error>1e-10:raise ValueError('Independent particular-field input differs')
        residual=reaction.vec.CreateVector();form.Apply(reaction.vec,residual)
        initial=float(np.linalg.norm(residual.FV().NumPy()[free]))
        if not np.isfinite(initial) or initial<=0:raise ValueError('Missing nonzero material response residual')
        save();solve_started=time.monotonic()
        result=NewtonMinimization(form,reaction,freedofs=selected,maxit=80,maxerr=1e-12,
            inverse='sparsecholesky',linesearch=True,printing=True)
        form.Apply(reaction.vec,residual);relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/initial
        report.update(newton_result=list(result),relative_equation_residual=relative,solve_seconds=time.monotonic()-solve_started)
        if result[0]!=0 or not np.isfinite(relative) or relative>1e-9:raise ValueError('Nonlinear vector equilibrium did not converge')
        reaction.Save(str(work/'reaction.sol'))
        report['solution_sha256']=sha(work/'reaction.sol')
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Vector material implementation changed during solve')
        if sha(origin/'summary.json')!=report['source_summary_sha256']:raise ValueError('Original material/source report changed')
        report.update(status='completed-static-vector-material-response-unqualified',seconds=time.monotonic()-started);save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


def load(work):
    import ngsolve as ng
    from netgen.read_gmsh import ReadGmsh
    from compare_reduced_fields import completed_receipt
    report=json.loads((work/'summary.json').read_text());completed_receipt(report)
    if report['status']!='completed-static-vector-material-response-unqualified' or report['failures']:
        raise ValueError('Need a completed vector equilibrium, not a partial trial')
    if ng.__version__!=report['version'] or sha(work/'project.msh')!=report['mesh_sha256'] or sha(work/'reaction.sol')!=report['solution_sha256']:
        raise ValueError('Vector solution version, mesh or field changed')
    mesh=ng.Mesh(ReadGmsh(str(work/'project.msh')));fes=ng.HCurl(mesh,order=report['order'],nograds=True,dirichlet=report['tangential_dirichlet'])
    reaction=ng.GridFunction(fes);reaction.Load(str(work/'reaction.sol'))
    return ng,report,mesh,fes,reaction


def total_field(work):
    ng,report,mesh,fes,reaction=load(work);particular=source_field(report['model']);curl=ng.curl(reaction)
    def evaluate(points):
        points=np.asarray(points,dtype=float);result=np.zeros_like(points)
        for start in range(0,len(points),16384):
            chunk=points[start:start+16384];folded=chunk.copy()
            if report['quarter_symmetry']:folded[:,:2]=abs(folded[:,:2])
            sampled=np.asarray(curl(mesh(folded[:,0],folded[:,1],folded[:,2]))).reshape(-1,3)
            if report['quarter_symmetry']:sampled[:,:2]*=np.sign(chunk[:,:2])
            result[start:start+16384]=particular(chunk)+sampled
        if not np.isfinite(result).all():raise ValueError('Nonfinite static vector field')
        return result
    return report,evaluate


if __name__=='__main__':threaded_main(main)
