#!/usr/bin/env python3
"""Finite 3D A-v induction benchmark, not a motor/housing-motion prediction.

At weak induction, an isolated disk in uniform Bz=Bpk*cos(omega*t) has
Jtheta_pk=-sigma*omega*Bpk*r/2 and mean loss pi*sigma*omega^2*Bpk^2*t*a^4/16.
The low-frequency limit is independent of FEMM and of the layered reflection.
The radial-slot case tests current rerouting and has no closed-form loss claim.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from check_free_space import run
from read_vtu import values, sample_vector

HERE=Path(__file__).resolve().parent
MU0=4e-7*math.pi


def weak_loss(frequency, peak_b, conductivity, radius, thickness):
    return math.pi*conductivity*(2*math.pi*frequency)**2*peak_b**2*thickness*radius**4/16


def sif(frequency, peak_b, conductivity):
    return f'''Include "mesh/mesh.names"
Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Max Output Level = 5
  Angular Frequency = {2*math.pi*frequency:.17g}
End
Constants
  Permeability of Vacuum = {MU0:.17g}
End
Body 1
  Target Bodies(1) = $ air
  Equation = 1
  Material = 1
End
Body 2
  Target Bodies(1) = $ conductor
  Equation = 1
  Material = 2
End
Material 1
  Relative Permeability = 1
  Relative Permittivity = 1
  Electric Conductivity = 0
End
Material 2
  Relative Permeability = 1
  Relative Permittivity = 1
  Electric Conductivity = {conductivity:.17g}
End
Equation 1
  Active Solvers(3) = 1 2 3
End
Solver 1
  Equation = MGDynamics
  Procedure = "MagnetoDynamics" "WhitneyAVHarmonicSolver"
  Variable = "AV[AV re:1 AV im:1]"
  Optimize Bandwidth = False
  Use Piola Transform = True
  Use Tree Gauge = False
  Fix Input Current Density = False
  Linear System Complex = True
  Linear System Symmetric = True
  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStabL
  BiCGStabL Polynomial Degree = 4
  Linear System Preconditioning = ILU0
  Linear System Convergence Tolerance = 1e-10
  Linear System Max Iterations = 5000
  Linear System Abort Not Converged = True
  Linear System Residual Output = 50
End
Solver 2
  Equation = MGDynamicsCalc
  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"
  Potential Variable = AV
  Optimize Bandwidth = False
  Calculate Magnetic Flux Density = True
  Calculate Magnetic Field Strength = True
  Calculate Current Density = True
  Calculate Electric Field = True
  Calculate Joule Heating = True
  Calculate Harmonic Peak Power = False
  Calculate Nodal Fields = True
  Calculate Elemental Fields = True
  Discontinuous Bodies = True
  Linear System Solver = Iterative
  Linear System Iterative Method = CG
  Linear System Symmetric = True
  Linear System Preconditioning = Diagonal
  Linear System Convergence Tolerance = 1e-11
  Linear System Max Iterations = 5000
  Linear System Abort Not Converged = True
  Linear System Residual Output = 0
End
Solver 3
  Exec Solver = After All
  Equation = ResultOutput
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = fields
  Vtu Format = True
  Binary Output = False
  Save Geometry IDs = True
  Discontinuous Bodies = True
End
Boundary Condition 1
  Target Boundaries(1) = $ outer
  AV Re {{e}} 1 = Variable Coordinate 2
    Real MATC "{-peak_b/2:.17g}*tx"
  AV Re {{e}} 2 = Variable Coordinate 1
    Real MATC "{peak_b/2:.17g}*tx"
  AV Re {{e}} 3 = Real 0
  AV Im {{e}} 1 = Real 0
  AV Im {{e}} 2 = Real 0
  AV Im {{e}} 3 = Real 0
End
'''


def mean_power(path):
    piece=ET.parse(path).getroot().find('./UnstructuredGrid/Piece')
    points=values(piece.find('./Points/DataArray')).reshape(-1,3)
    cells={a.get('Name'):values(a) for a in piece.findall('./Cells/DataArray')}
    offsets=np.r_[0,cells['offsets']]
    selected=np.flatnonzero(cells['types']==10)
    tetra=np.array([cells['connectivity'][offsets[i]:offsets[i+1]] for i in selected])
    vertices=points[tetra]
    volumes=np.abs(np.linalg.det(vertices[:,1:]-vertices[:,:1]))/6
    arrays={a.get('Name','').casefold():a for a in piece.findall('./CellData/DataArray')}
    point_arrays={a.get('Name','').casefold():a for a in piece.findall('./PointData/DataArray')}
    key='joule heating e'
    if key in arrays:
        heat=values(arrays[key])[selected]
    elif key in point_arrays:
        # Discontinuous Bodies writes element fields on duplicated cell nodes.
        heat=values(point_arrays[key])[tetra].mean(axis=1)
    else:
        raise ValueError(f'Missing elemental mean Joule heating; fields: {list(arrays)}')
    if not np.isfinite(heat).all():raise ValueError('Non-finite projected Joule density')
    power=float(volumes@heat)
    negative=float(volumes@np.minimum(heat,0))
    # L2 projection is not positivity preserving. Retain the signed integral;
    # reject meaningful negative projected energy, not harmless local ringing.
    if power<=0 or abs(negative)>1e-6*power:
        raise ValueError('Negative projected Joule energy exceeds one part per million')
    metadata={k:dict(v.attrib) for k,v in arrays.items()}
    metadata['_projection_audit']={'negative_power_w':negative,'negative_fraction':abs(negative)/power,
                                   'signed_integral_retained':True}
    return power,metadata


def poynting_input(path, radius):
    piece=ET.parse(path).getroot().find('./UnstructuredGrid/Piece')
    points=values(piece.find('./Points/DataArray')).reshape(-1,3)
    arrays={a.get('Name','').casefold():a for a in piece.findall('./PointData/DataArray')}
    def vector(name):
        a=values(arrays[name]).reshape(-1,3)
        if a.shape!=points.shape or not np.isfinite(a).all():raise ValueError('Invalid complex air field')
        return a
    e=vector('electric field re e')+1j*vector('electric field im e')
    h=vector('magnetic field strength re e')+1j*vector('magnetic field strength im e')
    cells={a.get('Name'):values(a) for a in piece.findall('./Cells/DataArray')}
    offsets=np.r_[0,cells['offsets']]
    outer=abs(np.linalg.norm(points,axis=1)-radius)<1e-8
    faces={}
    for i in np.flatnonzero(cells['types']==10):
        tetra=cells['connectivity'][offsets[i]:offsets[i+1]]
        for local in [(0,1,2),(0,1,3),(0,2,3),(1,2,3)]:
            nodes=tetra[list(local)]
            if not outer[nodes].all():continue
            key=tuple(sorted(tuple(p) for p in points[nodes]))
            faces.setdefault(key,[]).append(nodes)
    flux=0.;area_sum=0.;normal_sum=np.zeros(3);count=0
    barycentric=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
    for shared in faces.values():
        if len(shared)!=1:continue
        nodes=shared[0];a,b,c=points[nodes]
        normal=np.cross(b-a,c-a)/2
        if normal@((a+b+c)/3)<0:normal=-normal
        eq=barycentric@e[nodes];hq=barycentric@h[nodes]
        s=0.5*np.real(np.cross(eq,np.conjugate(hq))).mean(axis=0)
        flux+=float(s@normal)
        normal_sum+=normal;area_sum+=np.linalg.norm(normal);count+=1
    if count<4 or np.linalg.norm(normal_sum)>1e-8*area_sum:
        raise ValueError('Incomplete closed outer surface for Poynting flux')
    return -flux,count


def source_input_work(path, frequency, peak_b):
    """Mean impressed-field work: Re integral(conj(J) . Eprimary)/2.

    For the closed nonmagnetic conductor, self-field work is reactive and
    potential-gradient work vanishes by current continuity/no-flux boundaries.
    Integrate the product of linear fields exactly on each tetrahedron.
    """
    piece=ET.parse(path).getroot().find('./UnstructuredGrid/Piece')
    points=values(piece.find('./Points/DataArray')).reshape(-1,3)
    arrays={a.get('Name','').casefold():a for a in piece.findall('./PointData/DataArray')}
    ji=values(arrays['current density im e']).reshape(-1,3)
    cells={a.get('Name'):values(a) for a in piece.findall('./Cells/DataArray')}
    offsets=np.r_[0,cells['offsets']]
    tetra=np.array([cells['connectivity'][offsets[i]:offsets[i+1]] for i in np.flatnonzero(cells['types']==10)])
    v=points[tetra]
    volumes=np.abs(np.linalg.det(v[:,1:]-v[:,:1]))/6
    ep=2*math.pi*frequency*peak_b/2*np.stack([v[:,:,1],-v[:,:,0],np.zeros(v.shape[:2])],axis=2)
    j=ji[tetra]
    average=((j.sum(axis=1)*ep.sum(axis=1)).sum(axis=1)+(j*ep).sum(axis=(1,2)))/20
    return float(0.5*volumes@average)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['gmsh','elmer','elmergrid','work']:
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--frequency',type=float,nargs='+',default=[1,2])
    parser.add_argument('--peak-b',type=float,default=0.01)
    parser.add_argument('--conductivity',type=float,default=25e6)
    parser.add_argument('--disk-radius',type=float,default=0.006)
    parser.add_argument('--thickness',type=float,default=0.001)
    parser.add_argument('--mesh',type=float,default=0.0008)
    parser.add_argument('--air-radius',type=float,default=0.03)
    parser.add_argument('--air-mesh',type=float,default=0.004)
    parser.add_argument('--slot',type=float,default=0)
    parser.add_argument('--reuse-completed',action='store_true',help='reuse only an identical archived mesh/SIF with a completed solver receipt')
    args=parser.parse_args()
    if not (min(args.frequency)>0 and args.peak_b>0 and args.conductivity>0 and 0<args.mesh<args.disk_radius<args.air_radius and
            0<args.thickness<args.disk_radius and 0<=args.slot<args.disk_radius and 0<args.air_mesh<args.air_radius):
        parser.error('invalid excitation, geometry or mesh')
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    request={k:v for k,v in vars(args).items() if not isinstance(v,Path)}
    report={'scope':__doc__,'status':'running','request':request,'runs':{},'failures':[],
            'unqualified_quantities':['exterior electric field and Poynting flux']}
    (work/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.copyfile(HERE/'eddy_disk.geo',work/'disk.geo')
    command=[str(args.gmsh.resolve()),'disk.geo','-3','-format','msh2','-o','disk.msh','-v','4']
    for key,value in [('a',args.disk_radius),('thickness',args.thickness),('h',args.mesh),('radius',args.air_radius),('slot',args.slot),('far_mesh',args.air_mesh)]:
        command.extend(['-setnumber',key,str(value)])
    run(command,work,'mesh.log')
    for frequency in args.frequency:
        job=work/f'f{frequency:g}';job.mkdir(exist_ok=True)
        text=sif(frequency,args.peak_b,args.conductivity)
        receipt=job/'solve.log.command.json'
        reuse=False
        if args.reuse_completed and receipt.exists() and (job/'case.sif').exists() and (job/'disk.msh').exists() and (job/'solve.log').exists():
            previous=json.loads(receipt.read_text())
            reuse=(previous.get('status')=='completed' and previous.get('exit_code')==0 and
                   previous.get('command')==[str(args.elmer.resolve()),'case.sif'] and
                   (job/'case.sif').read_text()==text and
                   hashlib.sha256((job/'disk.msh').read_bytes()).digest()==hashlib.sha256((work/'disk.msh').read_bytes()).digest() and
                   'ELMER SOLVER FINISHED AT:' in (job/'solve.log').read_text() and
                   len(list(job.glob('**/fields*.vtu')))==1)
        if reuse:
            elapsed=previous['seconds']
        else:
            shutil.copyfile(work/'disk.msh',job/'disk.msh')
            (job/'case.sif').write_text(text)
            run([str(args.elmergrid.resolve()),'14','2','disk.msh','-out','mesh','-autoclean'],job,'convert.log')
            elapsed=run([str(args.elmer.resolve()),'case.sif'],job,'solve.log')
        files=list(job.glob('**/fields*.vtu'))
        assert len(files)==1,files
        power,fields=mean_power(files[0])
        matches=re.findall(r'Eddy current power:\s*([+\-\d.Ee]+)',(job/'solve.log').read_text())
        assert matches,'No integrated mean eddy power in solver log'
        logged=float(matches[-1])
        assert power>0 and abs(power/logged-1)<0.02,'Joule field / solver-integral discrepancy exceeds 2%'
        expected=weak_loss(frequency,args.peak_b,args.conductivity,args.disk_radius,args.thickness)
        induction=MU0*args.conductivity*2*math.pi*frequency*args.disk_radius**2
        error=power/expected-1
        if not args.slot and induction<=0.02 and abs(error)>0.05:
            report['failures'].append(f'{frequency:g} Hz: weak-induction loss error {error:.2%} exceeds 5%')
        angle=np.arange(12)*2*math.pi/12
        observations=np.column_stack([0.75*args.disk_radius*np.cos(angle),0.75*args.disk_radius*np.sin(angle),np.zeros(12)])
        # The slot crosses +x, so omit its two neighbouring samples there.
        if args.slot:
            observations=observations[(observations[:,0]<0)|(abs(observations[:,1])>args.slot)]
        # Raw element currents avoid smoothing Cu currents into adjacent air.
        jr=sample_vector(files[0],observations,'current density re e')
        ji=sample_vector(files[0],observations,'current density im e')
        reference=args.conductivity*2*math.pi*frequency*args.peak_b/2*np.column_stack([observations[:,1],-observations[:,0],np.zeros(len(observations))])
        current_error=float(np.sqrt(np.linalg.norm(jr)**2+np.linalg.norm(ji-reference)**2)/np.linalg.norm(reference))
        incident=sample_vector(files[0],[[0,0,0.003]],'magnetic flux density re')[0]
        incident_error=float(np.linalg.norm(incident-[0,0,args.peak_b])/args.peak_b)
        input_power,outer_faces=poynting_input(files[0],args.air_radius)
        source_power=source_input_work(files[0],frequency,args.peak_b)
        if abs(source_power/power-1)>0.02:
            report['failures'].append(f'{frequency:g} Hz: impressed-field work / Joule balance exceeds 2%')
        if not args.slot and induction<=0.02:
            if current_error>0.05:report['failures'].append(f'{frequency:g} Hz: current phasor error {current_error:.2%} exceeds 5%')
            if incident_error>0.01:report['failures'].append(f'{frequency:g} Hz: applied-field error {incident_error:.2%} exceeds 1%')
        result={'mean_power_w':power,'logged_power_w':logged,'weak_limit_power_w':expected,'weak_limit_relative_error':error,
                'solver_receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),
                'current_phasor_relative_error':current_error,'incident_field_relative_error':incident_error,
                'poynting_input_w':input_power,'poynting_balance_relative_error':input_power/power-1,'outer_faces':outer_faces,
                'source_input_work_w':source_power,'source_work_balance_relative_error':source_power/power-1,
                'weak_reference_scope':'intact disk only' if args.slot else 'same intact disk',
                'induction_parameter':induction,'solve_seconds':elapsed,'solution_reused':reuse,'cell_fields':fields,
                'sha256':{p:hashlib.sha256((job/p).read_bytes()).hexdigest() for p in ['disk.msh','case.sif','solve.log']}}
        report['runs'][str(frequency)]=result
        print(frequency,json.dumps(result),flush=True)
        (work/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    report['status']='failed' if report['failures'] else 'comparison-only'
    (work/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))
    print('Completed finite A-v induction diagnostic. Refinement and current-closure checks remain.')


if __name__=='__main__':
    main()
