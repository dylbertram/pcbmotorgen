#!/usr/bin/env python3
"""Independent NGSolve energy/automatic-tangent check of reduced static fields.

Uses an archived, validated physical Gmsh mesh, but independent H1 basis,
nonlinear assembly, automatic differentiation and energy line search. The PM
source is analytical in both implementations; this is NOT an independent PM
source-physics check or a winding/current/motion solver. No production dependency.
"""
import argparse
import itertools
import json
import shutil
import time
from pathlib import Path

import numpy as np

from post_project_force import sha
from project_static import validate_mesh
from project_symmetry import validate_quarter_mesh
from reduced_potential import MU0, source_field
from source_snapshot import capture
from solver_threads import add_thread_option,runtime_metadata,threaded_main


def source_coefficient(ng,model):
    total=ng.CoefficientFunction((0.,0.,0.))
    for magnet in model['magnets']:
        br=magnet['polarization_t']
        if br[:2]!=[0,0]:raise ValueError('Only axial cuboid sources are supported')
        for i,j,k in itertools.product([0,1],repeat=3):
            x=ng.x-(magnet['origin_m'][0]+i*magnet['size_m'][0])
            y=ng.y-(magnet['origin_m'][1]+j*magnet['size_m'][1])
            z=ng.z-(magnet['origin_m'][2]+k*magnet['size_m'][2])
            r=ng.sqrt(x*x+y*y+z*z)
            total+=br[2]*(-1)**(i+j+k)/(4*np.pi)*ng.CoefficientFunction((ng.log(y+r),ng.log(x+r),-ng.atan2(x*y,z*r)))
    return total


def energy_density(ng,gradient,source_h,mu,bsat,linear=False):
    if mu==1:return .5*ng.InnerProduct(gradient,gradient)
    h=source_h-gradient;squared=ng.InnerProduct(h,h)
    if linear or bsat is None:coenergy=.5*mu*squared
    else:
        knee=bsat/(MU0*(mu-1))
        # The saturated branch is inactive at H=0. Give its square-root
        # derivative a harmless finite argument there, without changing the
        # selected energy or tangent at any H.
        radius=ng.sqrt(ng.IfPos(squared,squared,1.))
        coenergy=ng.IfPos(squared-knee*knee,
            .5*squared+(bsat/MU0)*radius-bsat*knee/(2*MU0),.5*mu*squared)
    return coenergy+ng.InnerProduct(source_h,gradient)


def energy_form(ng,mesh,fes,model,solver_model,linear,bonus_order):
    # The particular source is immutable and independent of the trial field.
    # Flatten its expression DAG and cache source values per integration rule;
    # otherwise automatic Hessian assembly repeatedly walks hundreds of log /
    # atan nodes whose derivatives with respect to psi are all zero.
    bsource=source_coefficient(ng,model).Compile()
    hsource=ng.CacheCF(bsource/MU0)
    trial=fes.TrialFunction();gradient=ng.grad(trial)
    form=ng.BilinearForm(fes,symmetric=True)
    form+=ng.Variation(.5*ng.InnerProduct(gradient,gradient)*ng.dx(definedon=mesh.Materials('air'),bonus_intorder=bonus_order))
    for material in solver_model['stack']:
        density=energy_density(ng,gradient,hsource,material['mu_r'],material['bsat_t'],linear).Compile()
        form+=ng.Variation(density*ng.dx(definedon=mesh.Materials(material['name']),bonus_intorder=bonus_order))
    return form,bsource


def prepare(ng,work,order):
    from netgen.read_gmsh import ReadGmsh
    mesh=ng.Mesh(ReadGmsh(str(work/'project.msh')))
    if 'outer' not in mesh.GetBoundaries():raise ValueError('Missing exterior Dirichlet boundary')
    fes=ng.H1(mesh,order=order,dirichlet='outer')
    solution=ng.GridFunction(fes,name='psi')
    return mesh,fes,solution


def load_solution(work):
    import ngsolve as ng
    summary=json.loads((work/'summary.json').read_text())
    if summary.get('status')!='completed-ngsolve-reduced-response-unqualified' or summary.get('failures')!=[]:
        raise ValueError('Need a completed independent NGSolve response, not a partial/failed job')
    receipt=json.loads(Path(summary['command_receipt']).read_text())
    if receipt.get('status')!='completed' or receipt.get('exit_code')!=0:
        raise ValueError('Independent supervisor receipt is incomplete or failed')
    if str(work.resolve()) not in receipt.get('command',[]):raise ValueError('Independent receipt belongs to a different job')
    if ng.__version__!=summary['version']:raise ValueError('Reload the independent solution with its pinned NGSolve version')
    if sha(work/'project.msh')!=summary['mesh_sha256'] or sha(work/'psi.sol')!=summary['solution_sha256']:
        raise ValueError('Independent mesh or solution changed')
    if summary['relative_gradient_residual']>1e-9 or summary['source_coefficient_error_t']>1e-10:
        raise ValueError('Independent source or nonlinear convergence check failed')
    mesh,fes,solution=prepare(ng,work,summary['order']);solution.Load(str(work/'psi.sol'))
    return ng,summary,mesh,fes,solution


def total_field(work):
    ng,summary,mesh,fes,solution=load_solution(work)
    incident=source_field(summary['model']);gradient=ng.grad(solution)
    def evaluate(points):
        points=np.asarray(points,dtype=float);result=np.zeros_like(points)
        for start in range(0,len(points),16384):
            chunk=points[start:start+16384];folded=chunk.copy()
            if summary['quarter_symmetry']:folded[:,:2]=abs(folded[:,:2])
            sampled=np.asarray(gradient(mesh(folded[:,0],folded[:,1],folded[:,2])),dtype=float).reshape(-1,3)
            if summary['quarter_symmetry']:sampled[:,:2]*=np.sign(chunk[:,:2])
            result[start:start+16384]=incident(chunk)-MU0*sampled
        if not np.isfinite(result).all():raise ValueError('Nonfinite independent total field')
        return result
    return summary,evaluate


def seed_response(ng,mesh,solution,seed_work,source,order,linear):
    """Interpolate a completed response as an initial guess, not new evidence.

    Taper inside the old exterior so expansion never samples outside its FE
    support. No material law, source or new-domain equation is changed.
    """
    _,seed,old_mesh,old_fes,old_solution=load_solution(seed_work)
    if seed['model']!=source['model'] or seed['quarter_symmetry']!=source['quarter_symmetry'] or seed['order']!=order or seed['linear_material']!=linear:
        raise ValueError('Initial guess has different physical inputs, symmetry or basis order')
    radius=seed['air_radius_m'];r=ng.sqrt(ng.x**2+ng.y**2+ng.z**2)
    initial=ng.IfPos(.9*radius-r,old_solution*ng.IfPos(.8*radius-r,1.,(.9*radius-r)/(.1*radius)),0.)
    solution.Set(initial)
    if not np.isfinite(solution.vec.FV().NumPy()).all():raise ValueError('Nonfinite transferred initial guess')
    return {'source_work':str(seed_work.resolve()),'summary_sha256':sha(seed_work/'summary.json'),
        'solution_sha256':sha(seed_work/'psi.sol'),'taper_radii_m':[.8*radius,.9*radius],
        'scope':'Completed response interpolated as initial guess only; all new-domain equations must reconverge'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--order',type=int,default=2);parser.add_argument('--bonus-order',type=int,default=4)
    parser.add_argument('--command-receipt',type=Path,required=True)
    parser.add_argument('--linear',action='store_true')
    parser.add_argument('--initial-work',type=Path,help='completed same-physics response for an explicitly recorded initial guess')
    add_thread_option(parser)
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous independent trials')
    if not 1<=args.order<=4 or not 0<=args.bonus_order<=12:parser.error('Invalid basis or integration order')
    source=json.loads((origin/'summary.json').read_text())
    if source.get('status')!='completed-reduced-response-fields-unqualified' or source.get('failures')!=[]:
        raise ValueError('Need a completed source mesh/input job, not a partial/failed study')
    if sha(origin/'project.msh')!=source['mesh_sha256']:raise ValueError('Source mesh changed')
    validate_mesh(origin/'project.msh',source['solver_geometry_model'],source['air_radius_m'])
    if source['quarter_symmetry']:validate_quarter_mesh(origin/'project.msh')
    work.mkdir(parents=True);shutil.copy2(origin/'project.msh',work/'project.msh')
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    report={'status':'running','scope':__doc__,'backend':'NGSolve','version':ng.__version__,'execution':runtime_metadata(),
        'model':source['model'],'solver_geometry_model':source['solver_geometry_model'],'quarter_symmetry':source['quarter_symmetry'],
        'air_radius_m':source['air_radius_m'],'order':args.order,'bonus_integration_order':args.bonus_order,
        'linear_material':args.linear,'source_summary_sha256':sha(origin/'summary.json'),'mesh_sha256':sha(work/'project.msh'),'failures':[]}
    report['immutable_source_coefficient_cache']=True
    report['command_receipt']=str(args.command_receipt.resolve())
    report['source_snapshots']=capture(work,[Path(__file__),*[Path(__file__).parent/name for name in ['reduced_potential.py','project_static.py','project_symmetry.py','solver_threads.py']]])
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        mesh,fes,solution=prepare(ng,work,args.order)
        expected={'air',*[m['name'] for m in source['solver_geometry_model']['stack']]}
        if set(mesh.GetMaterials())!=expected:raise ValueError('Imported material names do not match the original model')
        report['dofs']=fes.ndof
        form,bsource=energy_form(ng,mesh,fes,source['model'],source['solver_geometry_model'],args.linear,args.bonus_order)
        table=np.loadtxt(origin/'bare/source.txt');points=table[:,:3]
        values=np.asarray(bsource(mesh(points[:,0],points[:,1],points[:,2])),dtype=float).reshape(-1,3)
        error=float(np.max(abs(values-source_field(source['model'])(points))))
        report['source_coefficient_error_t']=error
        if error>1e-10:raise ValueError('Independent analytical source disagrees with Magpylib')
        residual=solution.vec.CreateVector();free=np.array(fes.FreeDofs(),dtype=bool)
        start=time.monotonic()
        form.Apply(solution.vec,residual);initial=float(np.linalg.norm(residual.FV().NumPy()[free]))
        report['initial_residual_seconds']=time.monotonic()-start
        if not np.isfinite(initial) or initial<=0:raise ValueError('Missing nonzero independent material-response residual')
        save()
        print('Initial material residual assembled in',report['initial_residual_seconds'],'seconds',flush=True)
        if args.initial_work:
            report['initial_guess']=seed_response(ng,mesh,solution,args.initial_work.resolve(),source,args.order,args.linear)
            form.Apply(solution.vec,residual)
            report['initial_guess_relative_gradient_residual']=float(np.linalg.norm(residual.FV().NumPy()[free]))/initial
            save();print('Transferred initial response; relative gradient residual',report['initial_guess_relative_gradient_residual'],flush=True)
        start=time.monotonic()
        result=NewtonMinimization(form,solution,maxit=100,maxerr=1e-12,inverse='sparsecholesky',linesearch=True,printing=True)
        form.Apply(solution.vec,residual)
        relative=float(np.linalg.norm(residual.FV().NumPy()[free])/initial)
        report.update(newton_result=list(result),relative_gradient_residual=relative)
        report['newton_seconds']=time.monotonic()-start
        if result[0]!=0 or not np.isfinite(relative) or relative>1e-9:raise ValueError('Independent nonlinear residual gate failed')
        solution.Save(str(work/'psi.sol'));report['solution_sha256']=sha(work/'psi.sol')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Independent implementation changed during solve')
        if sha(origin/'summary.json')!=report['source_summary_sha256'] or sha(origin/'project.msh')!=report['mesh_sha256']:
            raise ValueError('Original physical inputs changed during independent solve')
        if args.initial_work and (sha(args.initial_work/'summary.json')!=report['initial_guess']['summary_sha256'] or
            sha(args.initial_work/'psi.sol')!=report['initial_guess']['solution_sha256']):
            raise ValueError('Initial-guess source changed during solve')
        report['status']='completed-ngsolve-reduced-response-unqualified';save()
        print(json.dumps({'dofs':report['dofs'],'relative_gradient_residual':relative,'source_coefficient_error_t':error}),flush=True)
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise


if __name__=='__main__':threaded_main(main)
