#!/usr/bin/env python3
"""Experimental current-free finite material response to analytical cuboid PMs.

H = H_source - grad(psi). In material the weak residual is
mu0*H_source - B(H_source-grad(psi)); in air it is mu0*grad(psi).
The fixed-remanence, mu_r=1 PM source cancels analytically in this change of
unknown, not by subtracting any failed FEM field/force. PM volumes therefore
need not be meshed for the response potential. Only response B in AIR is
exported. Total-field stress needs separate, refined nonlinear quadrature.

This is an offline prototype. No winding currents, AC or motion are solved.
"""
import argparse
import copy
import itertools
import json
from pathlib import Path

import magpylib as magpy
import numpy as np

from check_free_space import run
from mesh_controls import with_far_mesh
from mesh_stretch import stretched_geometry, physical_mesh
from post_project_force import sha
from project_static import project, validate_mesh, getdp_nonlinear_convergence
from project_symmetry import quarter_model, validate_quarter_mesh
from source_snapshot import capture
from reaction_mesh import with_observation_band

MU0=4e-7*np.pi
HERE=Path(__file__).resolve().parent


def source_field(model):
    magnets=[magpy.magnet.Cuboid(dimension=m['size_m'],polarization=m['polarization_t'],
        position=np.asarray(m['origin_m'])+np.asarray(m['size_m'])/2) for m in model['magnets']]
    def evaluate(points):
        points=np.asarray(points,dtype=float)
        if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Invalid source observations')
        result=np.zeros_like(points)
        for start in range(0,len(points),16384):
            result[start:start+16384]=sum(m.getB(points[start:start+16384]) for m in magnets)
        if not np.isfinite(result).all():raise ValueError('Source field is singular/nonfinite at the requested points')
        return result
    return evaluate


def source_functions(model):
    """Surface-charge corner sums, evaluated only outside the PMs.

    GetDP implements the elementary formula separately from Magpylib, used to
    audit it on material probes. Ideal PM edges are not observation points.
    """
    definitions=[];parts=[]
    for index,magnet in enumerate(model['magnets']):
        br=magnet['polarization_t']
        if br[:2]!=[0,0]:raise ValueError('This source expression requires axial cuboid polarization')
        for axis,name in enumerate('xyz'):
            for side in [0,1]:
                end=magnet['origin_m'][axis]+side*magnet['size_m'][axis]
                definitions.append(f's{index}{name}{side}[]={name.upper()}[]-({end:.17g});')
        terms=[[],[],[]]
        for i,j,k in itertools.product([0,1],repeat=3):
            x=f's{index}x{i}[]';y=f's{index}y{j}[]';z=f's{index}z{k}[]'
            r=f's{index}r{i}{j}{k}'
            definitions.append(f'{r}[]=Sqrt[{x}^2+{y}^2+{z}^2];')
            sign='+' if (i+j+k)%2==0 else '-'
            terms[0].append(f'{sign}Log[{y}+{r}[]]')
            terms[1].append(f'{sign}Log[{x}+{r}[]]')
            terms[2].append(f'{"-" if sign=="+" else "+"}Atan2[{x}*{y},{z}*{r}[]]')
        parts.append(f'({br[2]:.17g}/(4*Pi))*Vector['+','.join(''.join(t) for t in terms)+']')
    if not parts:raise ValueError('Missing prescribed PM source')
    definitions.extend(['Bsource[]='+'+'.join(parts)+';','Hsource[]=Bsource[]/mu0;'])
    return '\n'.join(definitions)


def constitutive(h,mu,bsat):
    """B(H) and exact spatial tangent of the original reversible two-slope law."""
    h=np.asarray(h,dtype=float);norm=float(np.linalg.norm(h))
    if h.shape!=(3,) or not np.isfinite(h).all() or mu<1:raise ValueError('Invalid material input')
    if bsat is None or mu==1 or norm<=bsat/(MU0*(mu-1)):
        return MU0*mu*h,MU0*mu*np.eye(3)
    secant=MU0+bsat/norm
    return secant*h,secant*np.eye(3)-bsat*np.outer(h,h)/norm**3


def response_model(model,quarter,omit_inert=False):
    reduced=quarter_model(model) if quarter else copy.deepcopy(model)
    # The response medium is vacuum at the PMs. Their fixed Br field is the
    # analytical particular solution; removing their artificial mesh interfaces
    # does not remove any physical source or change their mu_r=1 assumption.
    reduced['magnets']=[]
    if omit_inert:
        # Conductivity has no role in this strictly static job. A mu_r=1
        # spacer/housing is vacuum for the response PDE, not a force source.
        # Its original geometry stays in model for complete-body force boxes.
        reduced['stack']=[m for m in reduced['stack'] if m['mu_r']!=1]
    if not reduced['stack']:raise ValueError('A finite material stack is required')
    return reduced


def formulation(model,solver_model):
    tags=','.join(str(m['tag']) for m in solver_model['stack'])
    functions=['mu0=4*Pi*1e-7;',source_functions(model)]
    for material in solver_model['stack']:
        tag=material['tag'];mu=material['mu_r'];bsat=material['bsat_t']
        if mu==1 or bsat is None:
            functions.extend([f'mu[Region[{tag}]]=(Mode==0) ? mu0 : mu0*{mu:.17g};',
                              f'tangent[Region[{tag}]]=TensorDiag[0,0,0];'])
        else:
            knee=bsat/(MU0*(mu-1))
            functions.extend([f'mu[Region[{tag}]]=(Mode==0) ? mu0 : ((Mode==1 || Norm[$1]<={knee:.17g}) ? mu0*{mu:.17g} : mu0+{bsat:.17g}/Norm[$1]);',
                f'tangent[Region[{tag}]]=(Mode!=2 || Norm[$1]<={knee:.17g}) ? TensorDiag[0,0,0] : -{bsat:.17g}/Norm[$1]^3*SquDyadicProduct[$1];'])
    layer=model['stack'][0];z=layer['origin_m'][2]+layer['size_m'][2]/2
    length,width=model['footprint_m'];x0=length*.013;x1=length*.441;y=width*.173
    return f'''// Analytical-source / reduced scalar response. No failed-floor subtraction.
DefineConstant[Mode=2,Relaxation=1];
Group {{ Air=Region[1]; Plate=Region[{{{tags}}}]; Domain=Region[{{1,{tags}}}]; Outer=Region[1001]; }}
Function {{
{chr(10).join(functions)}
}}
Constraint {{{{Name Boundary; Case {{{{Region Outer; Value 0;}}}}}}}}
Jacobian {{{{Name J; Case {{{{Region All; Jacobian Vol;}}}}}}}}
Integration {{{{Name I; Case {{{{Type Gauss; Case {{{{GeoElement Tetrahedron; NumberOfPoints 15;}}}}}}}}}}}}
FunctionSpace {{
  {{Name H1; Type Form0;
    BasisFunction {{
      {{Name sn; NameOfCoef pn; Function BF_Node; Support Domain; Entity NodesOf[All];}}
      {{Name se; NameOfCoef pe; Function BF_Node_2E; Support Domain; Entity EdgesOf[All];}}
    }}
    Constraint {{
      {{NameOfCoef pn; EntityType NodesOf; NameOfConstraint Boundary;}}
      {{NameOfCoef pe; EntityType EdgesOf; NameOfConstraint Boundary;}}
    }}
  }}
}}
Formulation {{
  {{Name PM; Type FemEquation; Quantity {{{{Name phi; Type Local; NameOfSpace H1;}}}}
    Equation {{
      Galerkin {{[mu0*Dof{{d phi}},{{d phi}}]; In Air; Jacobian J; Integration I;}}
      Galerkin {{[(Mode==0 ? mu0 : mu[Hsource[]-{{d phi}}])*Dof{{d phi}},{{d phi}}]; In Plate; Jacobian J; Integration I;}}
      Galerkin {{[(Mode==0 ? Vector[0,0,0] : (mu0-mu[Hsource[]-{{d phi}}])*Hsource[]),{{d phi}}]; In Plate; Jacobian J; Integration I;}}
      Galerkin {{JacNL [(Mode==0 ? TensorDiag[0,0,0] : tangent[Hsource[]-{{d phi}}])*Dof{{d phi}},{{d phi}}]; In Plate; Jacobian J; Integration I;}}
    }}
  }}
}}
Resolution {{
  {{Name SolvePM; System {{{{Name S; NameOfFormulation PM;}}}}
    Operation {{
      InitSolution[S];
      If(Mode==2)
        IterativeLoop[100,1e-9,Relaxation] {{GenerateJac[S];SolveJac[S];}}
        Print[{{$NLResidual,$NLIteration}},File "nonlinear.txt",Format "%.17g %.0f"];
        Test[$NLResidual>1e-9] {{Error["Reduced potential failed to converge"];}}
      Else
        GenerateJac[S];SolveJac[S];
      EndIf
      SaveSolution[S];PostOperation[Samples];
    }}
  }}
}}
PostProcessing {{
  {{Name Fields; NameOfFormulation PM;
    Quantity {{
      {{Name reaction; Value {{Local {{[-mu0*{{d phi}}];In Air;Jacobian J;}}}}}}
      {{Name source; Value {{Local {{[Bsource[]];In Domain;Jacobian J;}}}}}}
    }}
  }}
}}
PostOperation {{
  {{Name Samples; NameOfPostProcessing Fields;
    Operation {{
      Print[reaction,OnElementsOf Air,Format Gmsh,File "reaction.pos"];
      Print[source,OnLine {{{{{x0:.17g},{y:.17g},{z:.17g}}}{{{x1:.17g},{y:.17g},{z:.17g}}}}} {{31}},Format SimpleTable,File "source.txt"];
    }}
  }}
}}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--version',type=int,required=True)
    parser.add_argument('--footprint-mm',type=float,nargs=2,required=True);parser.add_argument('--array-centre-mm',type=float,nargs=2,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--gmsh',type=Path,required=True);parser.add_argument('--getdp',type=Path,required=True)
    parser.add_argument('--mesh',type=float,default=.0008);parser.add_argument('--gap-mesh',type=float,default=.0001)
    parser.add_argument('--radius',type=float,default=.06);parser.add_argument('--far-mesh',type=float,default=.01)
    parser.add_argument('--z-stretch',type=float,default=4.);parser.add_argument('--quarter',action='store_true')
    parser.add_argument('--bare-only',action='store_true');parser.add_argument('--linear',action='store_true')
    parser.add_argument('--relaxation',type=float,default=1.)
    parser.add_argument('--observation-mesh',type=float,help='independent CAD X/Y target in the mover observation band; default --mesh')
    parser.add_argument('--observation-band',type=float,default=.001,help='physical air-band reach around the original PM array, even though PM interfaces are not meshed')
    parser.add_argument('--newton-assembly',choices=['coefficient','explicit-residual'],default='coefficient')
    args=parser.parse_args();work=args.work.resolve()
    if not np.isfinite(args.relaxation) or not 0<args.relaxation<=1:parser.error('Relaxation must be finite and in (0,1]')
    if work.exists():parser.error('Preserve prior jobs; choose a new output directory')
    model=project(args.project,args.version,args.footprint_mm,args.array_centre_mm)
    solver_model=response_model(model,args.quarter,omit_inert=True)
    geo=with_far_mesh(stretched_geometry(solver_model,args.mesh,args.gap_mesh,args.radius,args.z_stretch,quarter=args.quarter),args.far_mesh)
    observation_mesh=args.mesh if args.observation_mesh is None else args.observation_mesh
    if not args.mesh<=args.far_mesh<args.radius or not 0<args.observation_band<args.radius:
        parser.error('Invalid far-air maximum or physical observation band')
    observation_model=quarter_model(model) if args.quarter else model
    geo=with_observation_band(geo,observation_model,observation_mesh,args.observation_band,args.z_stretch,args.far_mesh)
    text=formulation(model,solver_model)
    if args.newton_assembly=='explicit-residual':
        from reduced_residual_trial import explicit_formulation
        text=explicit_formulation(text,solver_model)
    work.mkdir(parents=True);(work/'project.geo').write_text(geo)
    report={'status':'running','method':'analytic-source-reduced-scalar-potential','scope':__doc__,
        'model':model,'solver_geometry_model':solver_model,'quarter_symmetry':args.quarter,'element_order':2,
        'mesh_m':args.mesh,'gap_mesh_m':args.gap_mesh,'far_mesh_m':args.far_mesh,'air_radius_m':args.radius,'z_stretch':args.z_stretch,
        'linear_material':args.linear,'bare_only':args.bare_only,'runs':{},'failures':[],
        'omit_inert_regions':True,'getdp_relaxation':args.relaxation,
        'observation_mesh_m':observation_mesh,'physical_observation_band_m':args.observation_band,
        'newton_assembly':args.newton_assembly,
        'getdp_executable_sha256':sha(args.getdp.resolve()),
        'limits':['PM source is analytical, not independently FEM-resolved','B response export is AIR-only',
                  'total-field force needs independent triangle quadrature refinement','no mesh/domain/backend qualification from one job']}
    paths=[args.project,Path(__file__),*[HERE/name for name in ['project_static.py','mesh_stretch.py','mesh_controls.py','reaction_mesh.py','project_symmetry.py','check_free_space.py','job_status.py']]]
    if args.newton_assembly=='explicit-residual':paths.append(HERE/'reduced_residual_trial.py')
    report['source_snapshots']=capture(work,paths);summary=work/'summary.json'
    def save():summary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        run([str(args.gmsh.resolve()),'project.geo','-3','-format','msh2','-o','scaled.msh','-v','4'],work,'mesh.log')
        physical_mesh(work/'scaled.msh',work/'project.msh',args.z_stretch,args.radius)
        report['material_volumes_m3']=validate_mesh(work/'project.msh',solver_model,args.radius)
        if args.quarter:report['symmetry_mesh_validation']=validate_quarter_mesh(work/'project.msh')
        report['mesh_sha256']=sha(work/'project.msh');save()
        for name,mode in [('bare',0),('stack',1 if args.linear else 2)]:
            job=work/name;job.mkdir();(job/'project.pro').write_text(text)
            elapsed=run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-solve','SolvePM','-v','4',
                '-setnumber','Mode',str(mode),'-setnumber','Relaxation',str(args.relaxation),'-ksp_type','cg','-pc_type','gamg','-ksp_rtol','1e-11','-ksp_max_it','2000',
                '-ksp_converged_reason','-ksp_error_if_not_converged'],job,'solve.log')
            if 'CONVERGED_' not in (job/'solve.log').read_text():raise ValueError('Missing linear convergence evidence')
            table=np.loadtxt(job/'source.txt')
            if table.shape!=(32,6) or not np.isfinite(table).all():raise ValueError('Invalid source-function audit')
            expected=source_field(model)(table[:,:3]);error=float(np.max(abs(expected-table[:,3:])))
            if error>1e-10:raise ValueError('GetDP analytical source disagrees with Magpylib')
            proof=getdp_nonlinear_convergence(job) if mode==2 else None
            report['runs'][name]={'mode':mode,'solve_seconds':elapsed,'source_function_error_t':error,
                'reaction_field_sha256':sha(job/'reaction.pos'),'formulation_sha256':sha(job/'project.pro'),'nonlinear_convergence':proof}
            save();print(name,json.dumps(report['runs'][name]),flush=True)
            if args.bare_only:break
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Input or implementation changed during the job')
        if sha(args.project)!=model['source_sha256']:raise ValueError('Project input changed during the job')
        report['status']='completed-reduced-response-fields-unqualified';save()
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise


if __name__=='__main__':main()
