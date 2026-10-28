#!/usr/bin/env python3
"""Bounded source continuation for the original reduced static equations.

Only the INITIAL GUESS is continued from weak source to the full prescribed
source. The final accepted field must use scale=1, the original material law
and original 1e-9 residual gate. Intermediate or failed stages are not usable
motor results. Source intensities are numerical continuation parameters, not
fitted remanence values. Previous FE coefficients stay on a byte-identical mesh.
"""
import argparse
import copy
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np

from check_free_space import run
from post_project_force import sha
from post_reduced_force import case_field
from project_static import getdp_nonlinear_convergence
from read_vtu import _vector_mesh, clear_vector_cache
from reduced_inputs import validate_reduced_inputs
from reduced_potential import source_field, source_functions
from reduced_residual_trial import explicit_formulation
from source_snapshot import capture


def solution_values(path):
    lines=path.read_text().splitlines();blocks=[i for i,row in enumerate(lines) if row.startswith('$Solution')]
    if len(blocks)!=1:raise ValueError('Need exactly one saved scalar solution')
    start=blocks[0]+2
    try:end=lines.index('$EndSolution',start)
    except ValueError as error:raise ValueError('Incomplete saved solution') from error
    values=np.array([list(map(float,row.split())) for row in lines[start:end]])
    if values.ndim!=2 or values.shape[1]!=2 or not len(values) or not np.isfinite(values).all() or np.max(abs(values[:,1]))>1e-30:
        raise ValueError('Expected a finite real scalar FE coefficient vector')
    return values[:,0]


def with_initial(text):
    marker='InitSolution[S];'
    if text.count(marker)!=1:raise ValueError('Unrecognized solution initialization')
    text='InitialValues()=ListFromFile["initial.txt"];\n'+text
    text=text.replace(marker,marker+' CopySolution[InitialValues(),S]; PostOperation[InitialSamples];')
    return text+'''\nPostOperation {
  {Name InitialSamples; NameOfPostProcessing Fields;
   Operation {Print[reaction,OnElementsOf Air,Format Gmsh,File "initial-reaction.pos"];}}
}\n'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--getdp',type=Path,required=True);parser.add_argument('--linear',action='store_true')
    parser.add_argument('--scales',type=float,nargs='+',default=[.001,.01,.1,.3,1.])
    parser.add_argument('--initial-from',type=Path);parser.add_argument('--overall-timeout',type=float,default=600.)
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous continuation trials')
    if not np.isfinite(args.scales).all() or args.scales[0]<=0 or args.scales[-1]!=1 or any(a>=b for a,b in zip(args.scales,args.scales[1:])):
        parser.error('Positive strictly increasing source scales ending exactly at 1 required')
    if not np.isfinite(args.overall_timeout) or args.overall_timeout<=0:parser.error('Positive finite time cap required')
    source=json.loads((origin/'summary.json').read_text());case_field(origin,source,'bare');validate_reduced_inputs(origin,source)
    nominal=source_functions(source['model']);base=(origin/'bare/project.pro').read_text()
    if base.count(nominal)!=1:raise ValueError('Original nominal source expression changed')
    if 'FluxResidual[' not in base:base=explicit_formulation(base,source['solver_geometry_model'])
    previous=None
    if args.initial_from:
        previous=args.initial_from.resolve()
        initial=json.loads((previous.parent/'summary.json').read_text())
        case_field(previous.parent,initial,previous.name)
        if initial['mesh_sha256']!=source['mesh_sha256'] or initial['model']!=source['model']:
            raise ValueError('Initial-guess case has different physical inputs/mesh')
    work.mkdir(parents=True)
    for name in ['project.msh','project.geo']:shutil.copy2(origin/name,work/name)
    shutil.copytree(origin/'source-snapshots',work/'source-snapshots')
    shutil.copytree(origin/'bare',work/'bare')
    report=copy.deepcopy(source)
    report.update(status='running',bare_only=False,linear_material=args.linear,failures=[],
        runs={'bare':source['runs']['bare']},stages=[],newton_assembly='explicit-residual-source-continuation',
        source_summary_sha256=sha(origin/'summary.json'),original_source_snapshots=source['source_snapshots'])
    report['bare_control_reused_from']=str(origin/'bare')
    report['source_snapshots']=capture(work,[Path(__file__),*[Path(__file__).parent/name for name in [
        'reduced_potential.py','reduced_residual_trial.py','reduced_inputs.py','check_free_space.py','project_static.py']]])
    summary=work/'summary.json'
    def save():summary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();start=time.monotonic();old_timeout=os.environ.get('PCB_MOTOR_SOLVER_TIMEOUT')
    try:
        for index,scale in enumerate(args.scales):
            remaining=args.overall_timeout-(time.monotonic()-start)
            if remaining<=0:raise TimeoutError('Overall continuation time cap exceeded')
            stage_name='stack' if scale==1 else f'continuation-{index}'
            job=work/stage_name;job.mkdir()
            scaled=copy.deepcopy(source['model'])
            for magnet in scaled['magnets']:magnet['polarization_t'][2]*=scale
            text=base.replace(nominal,source_functions(scaled))
            if previous is not None:
                values=solution_values(previous/'project.res')
                np.savetxt(job/'initial.txt',values,fmt='%.17g')
                text=with_initial(text)
            (job/'project.pro').write_text(text)
            os.environ['PCB_MOTOR_SOLVER_TIMEOUT']=str(min(remaining,180.))
            elapsed=run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-solve','SolvePM','-v','4',
                '-setnumber','Mode',str(1 if args.linear else 2),'-ksp_type','cg','-pc_type','gamg','-ksp_rtol','1e-11',
                '-ksp_max_it','2000','-ksp_converged_reason','-ksp_error_if_not_converged'],job,'solve.log')
            if 'CONVERGED_' not in (job/'solve.log').read_text():raise ValueError('Missing continuation linear convergence')
            if previous is not None:
                clear_vector_cache();a=previous/'reaction.pos';s=a.stat()
                va,ba,*_=_vector_mesh(str(a),s.st_mtime_ns,s.st_size,'response')
                b=job/'initial-reaction.pos';s=b.stat();vb,bb,*_=_vector_mesh(str(b),s.st_mtime_ns,s.st_size,'response')
                np.testing.assert_array_equal(va,vb)
                initial_error=float(np.linalg.norm(ba-bb)/max(np.linalg.norm(ba),1e-30))
                if initial_error>1e-10:raise ValueError('FE coefficient transfer changed the previous physical reaction field')
            else:initial_error=None
            table=np.loadtxt(job/'source.txt')
            if table.shape!=(32,6) or not np.isfinite(table).all():raise ValueError('Invalid continuation source audit')
            error=float(np.max(abs(table[:,3:]-source_field(scaled)(table[:,:3]))))
            if error>1e-10:raise ValueError('Continuation source differs from the declared scaled source')
            proof=None if args.linear else getdp_nonlinear_convergence(job)
            record={'scale':scale,'directory':stage_name,'mode':1 if args.linear else 2,'solve_seconds':elapsed,
                'source_function_error_t':error,'nonlinear_convergence':proof,'initial_field_transfer_relative_error':initial_error,
                'reaction_field_sha256':sha(job/'reaction.pos'),'formulation_sha256':sha(job/'project.pro')}
            report['stages'].append(record);save();print(json.dumps(record),flush=True)
            previous=job
        report['runs']['stack']=report['stages'][-1]
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Continuation implementation changed during solve')
        if sha(origin/'summary.json')!=report['source_summary_sha256']:raise ValueError('Original physical inputs changed')
        report['status']='completed-reduced-response-fields-unqualified';save()
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise
    finally:
        if old_timeout is None:os.environ.pop('PCB_MOTOR_SOLVER_TIMEOUT',None)
        else:os.environ['PCB_MOTOR_SOLVER_TIMEOUT']=old_timeout


if __name__=='__main__':main()
