#!/usr/bin/env python3
"""Test an explicit residual/full-tangent GetDP Newton formulation.

Reuses ONLY a completed prototype's immutable geometry/mesh/source expression.
The constitutive law and 1e-9 nonlinear gate are unchanged. This separates
GetDP nonlinear assembly semantics from geometry and source discretization.
No result from the earlier oscillating or timed-out trials is recovered.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path

import numpy as np

from check_free_space import run
from post_project_force import sha
from project_static import getdp_nonlinear_convergence, validate_mesh
from reduced_potential import source_field
from source_snapshot import capture


def explicit_formulation(text,model):
    declarations=[]
    for material in model['stack']:
        tag=material['tag']
        if material['mu_r']==1:
            residual='mu0*$1';jacobian='TensorDiag[mu0,mu0,mu0]'
        else:
            residual='(Mode==0 ? mu0*$1 : mu0*Hsource[]-mu[Hsource[]-$1]*(Hsource[]-$1))'
            jacobian='(Mode==0 ? TensorDiag[mu0,mu0,mu0] : mu[Hsource[]-$1]*TensorDiag[1,1,1]+tangent[Hsource[]-$1])'
        declarations.extend([f'FluxResidual[Region[{tag}]]={residual};',f'FullTangent[Region[{tag}]]={jacobian};'])
    marker='\nConstraint '
    position=text.find(marker)
    if position<0 or text[:position].rstrip()[-1]!='}':raise ValueError('Unrecognized source function block')
    last=text.rfind('}',0,position)
    text=text[:last]+'\n'+'\n'.join(declarations)+'\n'+text[last:]
    terms=[
        'Galerkin {[(Mode==0 ? mu0 : mu[Hsource[]-{d phi}])*Dof{d phi},{d phi}]; In Plate; Jacobian J; Integration I;}',
        'Galerkin {[(Mode==0 ? Vector[0,0,0] : (mu0-mu[Hsource[]-{d phi}])*Hsource[]),{d phi}]; In Plate; Jacobian J; Integration I;}',
        'Galerkin {JacNL [(Mode==0 ? TensorDiag[0,0,0] : tangent[Hsource[]-{d phi}])*Dof{d phi},{d phi}]; In Plate; Jacobian J; Integration I;}'
    ]
    for term in terms:
        if text.count(term)!=1:raise ValueError('Unrecognized original nonlinear assembly')
    text=text.replace(terms[0],'Galerkin {[FluxResidual[{d phi}],{d phi}]; In Plate; Jacobian J; Integration I;}')
    text=text.replace(terms[1],'Galerkin {JacNL [FullTangent[{d phi}]*Dof{d phi},{d phi}]; In Plate; Jacobian J; Integration I;}')
    return text.replace(terms[2],'// Full material residual and Jacobian assembled explicitly above.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--getdp',type=Path,required=True);parser.add_argument('--linear',action='store_true')
    parser.add_argument('--original-assembly',action='store_true',help='paired linear-control job without changing the original assembly')
    parser.add_argument('--relaxation',type=float,default=1.)
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve existing trials')
    if not np.isfinite(args.relaxation) or not 0<args.relaxation<=1:parser.error('Invalid Newton relaxation')
    source=json.loads((origin/'summary.json').read_text())
    if source.get('status')!='completed-reduced-response-fields-unqualified' or source.get('failures')!=[]:
        raise ValueError('Need a completed bare prototype as immutable input, not a failed material trial')
    if sha(origin/'project.msh')!=source['mesh_sha256']:raise ValueError('Source mesh changed')
    validate_mesh(origin/'project.msh',source['solver_geometry_model'],source['air_radius_m'])
    text=(origin/'bare/project.pro').read_text()
    if sha(origin/'bare/project.pro')!=source['runs']['bare']['formulation_sha256']:raise ValueError('Original source formulation changed')
    if not args.original_assembly:text=explicit_formulation(text,source['solver_geometry_model'])
    work.mkdir(parents=True)
    for name in ['project.msh','project.geo']:shutil.copy2(origin/name,work/name)
    shutil.copytree(origin/'source-snapshots',work/'source-snapshots')
    report=copy.deepcopy(source)
    report.update(status='running',bare_only=False,linear_material=args.linear,runs={},failures=[],
        source_summary_sha256=sha(origin/'summary.json'),newton_assembly='original-coefficient' if args.original_assembly else 'explicit-residual-full-tangent',
        getdp_relaxation=args.relaxation,original_source_snapshots=source['source_snapshots'])
    paths=[Path(__file__),*[Path(__file__).parent/name for name in ['check_free_space.py','project_static.py','reduced_potential.py']]]
    report['source_snapshots']=capture(work,paths)
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for name,mode in [('bare',0),('stack',1 if args.linear else 2)]:
            job=work/name;job.mkdir();(job/'project.pro').write_text(text)
            elapsed=run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-solve','SolvePM','-v','4',
                '-setnumber','Mode',str(mode),'-setnumber','Relaxation',str(args.relaxation),'-ksp_type','cg','-pc_type','gamg',
                '-ksp_rtol','1e-11','-ksp_max_it','2000','-ksp_converged_reason','-ksp_error_if_not_converged'],job,'solve.log')
            if 'CONVERGED_' not in (job/'solve.log').read_text():raise ValueError('Missing linear convergence')
            table=np.loadtxt(job/'source.txt')
            if table.shape!=(32,6) or not np.isfinite(table).all():raise ValueError('Invalid analytical source probes')
            error=float(np.max(abs(table[:,3:]-source_field(source['model'])(table[:,:3]))))
            if error>1e-10:raise ValueError('Analytical source check failed')
            proof=getdp_nonlinear_convergence(job) if mode==2 else None
            report['runs'][name]={'mode':mode,'solve_seconds':elapsed,'source_function_error_t':error,
                'reaction_field_sha256':sha(job/'reaction.pos'),'formulation_sha256':sha(job/'project.pro'),'nonlinear_convergence':proof}
            save();print(name,json.dumps(report['runs'][name]),flush=True)
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Trial implementation changed during solve')
        if sha(origin/'summary.json')!=report['source_summary_sha256']:raise ValueError('Original completed prototype changed')
        report['status']='completed-reduced-response-fields-unqualified';save()
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise


if __name__=='__main__':main()
