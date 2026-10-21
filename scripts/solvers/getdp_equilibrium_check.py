#!/usr/bin/env python3
"""Certify the assembled GetDP equations from a verified independent seed.

The legacy SolveJac/IterativeLoop printed metric is an update proxy, not the
assembled equation residual. This check uses ||b-A*x||_2 normalized by the same
full-source problem at zero response, requiring <=1e-9. No tolerance or physical
constant is relaxed. A shared seed is disclosed: this is a backend-equation
consistency check, NOT proof of independent cold-start convergence/runtime.
"""
import argparse
import copy
import json
import os
import re
import shutil
from pathlib import Path

import numpy as np

from check_free_space import run
from post_project_force import sha
from reduced_inputs import validate_reduced_inputs
from reduced_potential import source_field
from reduced_residual_trial import explicit_formulation
from source_snapshot import capture


def certificate(job):
    row=np.loadtxt(job/'equilibrium.txt').reshape(-1)
    if row.shape!=(4,) or not np.isfinite(row).all():raise ValueError('Invalid assembled-equilibrium certificate')
    relative,iteration,reference,residual=map(float,row)
    if not 0<=iteration<=30 or not iteration.is_integer() or reference<=0 or residual<0 or not 0<=relative<=1e-9:
        raise ValueError('Assembled-equilibrium residual gate failed')
    if not np.isclose(relative,residual/reference,rtol=1e-8,atol=1e-16):raise ValueError('Inconsistent residual normalization')
    return {'metric':'assembled-equation L2 residual / zero-response full-source residual',
        'relative_residual':relative,'iterations':int(iteration),'reference_norm':reference,'final_residual_norm':residual,
        'certificate_sha256':sha(job/'equilibrium.txt')}


def certified_formulation(text):
    if 'FluxResidual[' not in text:raise ValueError('Explicit residual/full-tangent formulation required')
    resolution='''Resolution {
 {Name SolvePM; System {{Name S;NameOfFormulation PM;}}
  Operation {
   InitSolution[S];
   GenerateJac[S];GetResidual[S,$CertReference];
   Test[$CertReference<=0] {Error["Missing nonzero full-source reference residual"];}
   CopySolution[InitialValues(),S];
   GenerateJac[S];GetResidual[S,$CertResidual];
   Evaluate[$CertIteration=0,$CertRelative=$CertResidual/$CertReference];
   Print[{$CertIteration,$CertRelative},File "equilibrium-trace.txt",Format "%.0f %.17g"];
   While[$CertRelative>1e-9 && $CertIteration<30] {
    SolveJac_AdaptRelax[S,{1,0.5,0.25,0.125,0.0625,0.03125},0];
    GenerateJac[S];GetResidual[S,$CertResidual];
    Evaluate[$CertIteration=$CertIteration+1,$CertRelative=$CertResidual/$CertReference];
    Print[{$CertIteration,$CertRelative},File "equilibrium-trace.txt",Format "%.0f %.17g"];
   }
   Print[{$CertRelative,$CertIteration,$CertReference,$CertResidual},File "equilibrium.txt",Format "%.17g %.0f %.17g %.17g"];
   Test[$CertRelative>1e-9] {Error["Assembled GetDP equilibrium failed to converge"];}
   SaveSolution[S];PostOperation[Samples];
  }
 }
}
'''
    result,count=re.subn(r'Resolution \{.*?(?=PostProcessing \{)',lambda _:resolution,text,count=1,flags=re.S)
    if count!=1:raise ValueError('Unrecognized source resolution')
    return 'InitialValues()=ListFromFile["initial.txt"];\n'+result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--seed-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--getdp',type=Path,required=True)
    args=parser.parse_args();origin=args.source_work.resolve();seed=args.seed_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous certificates and failed trials')
    source=json.loads((origin/'summary.json').read_text());validate_reduced_inputs(origin,source)
    from post_reduced_force import case_field
    case_field(origin,source,'bare')
    initial=json.loads((seed/'summary.json').read_text())
    if initial.get('status')!='verified-initial-guess-transfer-only' or initial.get('failures')!=[]:
        raise ValueError('Need the verified basis-transfer seed, not an unverified field')
    if initial['mesh_sha256']!=source['mesh_sha256'] or initial['source_summary_sha256']!=sha(origin/'summary.json'):
        raise ValueError('Seed belongs to a different physical input/mesh')
    if sha(seed/'initial.txt')!=initial['initial_values_sha256'] or sha(args.getdp.resolve())!=initial['getdp_executable_sha256']:
        raise ValueError('Seed coefficients or GetDP binary changed')
    template=(origin/'bare/project.pro').read_text()
    if 'FluxResidual[' not in template:template=explicit_formulation(template,source['solver_geometry_model'])
    text=certified_formulation(template)
    work.mkdir(parents=True)
    for name in ['project.msh','project.geo']:shutil.copy2(origin/name,work/name)
    shutil.copytree(origin/'bare',work/'bare');shutil.copytree(origin/'source-snapshots',work/'source-snapshots')
    job=work/'stack';job.mkdir();shutil.copy2(seed/'initial.txt',job/'initial.txt');(job/'project.pro').write_text(text)
    report=copy.deepcopy(source)
    report.update(status='running',bare_only=False,linear_material=False,runs={'bare':source['runs']['bare']},failures=[],
        newton_assembly='explicit-assembled-residual-certificate',shared_initial_guess=True,
        seed_summary_sha256=sha(seed/'summary.json'),independent_seed_source_summary_sha256=initial['independent_summary_sha256'],
        source_summary_sha256=sha(origin/'summary.json'),original_source_snapshots=source['source_snapshots'])
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    report['source_snapshots']=capture(work,[Path(__file__),*[Path(__file__).parent/name for name in [
        'reduced_residual_trial.py','reduced_potential.py','reduced_inputs.py','check_free_space.py']]])
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        elapsed=run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-solve','SolvePM','-v','4',
            '-setnumber','Mode','2','-ksp_type','cg','-pc_type','gamg','-ksp_rtol','1e-11','-ksp_max_it','2000',
            '-ksp_converged_reason','-ksp_error_if_not_converged'],job,'solve.log')
        proof=certificate(job)
        table=np.loadtxt(job/'source.txt')
        if table.shape!=(32,6) or not np.isfinite(table).all():raise ValueError('Invalid source-input audit')
        error=float(np.max(abs(table[:,3:]-source_field(source['model'])(table[:,:3]))))
        if error>1e-10:raise ValueError('Source physical parameters changed')
        report['runs']['stack']={'mode':2,'solve_seconds':elapsed,'source_function_error_t':error,
            'reaction_field_sha256':sha(job/'reaction.pos'),'formulation_sha256':sha(job/'project.pro'),
            'nonlinear_convergence':proof,'equilibrium_certificate':proof}
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Certificate implementation changed')
        if sha(origin/'summary.json')!=report['source_summary_sha256'] or sha(seed/'summary.json')!=report['seed_summary_sha256']:
            raise ValueError('Source/initial-guess report changed during certification')
        report['status']='completed-reduced-response-fields-unqualified';save();print(json.dumps(proof),flush=True)
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise


if __name__=='__main__':main()
