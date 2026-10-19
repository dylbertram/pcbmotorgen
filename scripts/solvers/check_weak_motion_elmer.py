#!/usr/bin/env python3
"""Steady A-v weak-motion comparison for a finite Al plate and one PM.

Conductor velocity is measured in the stationary-PM frame. The finite geometry
is a frozen instantaneous weak-induction diagnostic, not a moving-boundary
transient. Compare with the Magpylib/SciPy continuity oracle before accepting
low-speed drag. Do not extrapolate to operating speed or saturated backplanes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import magpylib as magpy
import numpy as np

from check_finite_plate import elmer_input, OBSERVATIONS, validate_mesh
from weak_motion import MU0
from check_free_space import run
from read_vtu import values, sample_vector

HERE=Path(__file__).resolve().parent


def input_file(velocity, sigma):
    text=elmer_input(0,130,0.25)
    original='''Body 3
  Target Bodies(1) = 3
  Equation = 1
  Material = 2
End'''
    replacement=original.replace('  Material = 2','  Material = 2\n  Body Force = 2')
    assert text.count(original)==1
    text=text.replace(original,replacement)
    original='''Material 2
  Relative Permeability = 1
  Electric Conductivity = 0
End'''
    assert text.count(original)==1
    text=text.replace(original,f'''Material 2
  Relative Permeability = 1
  Relative Permittivity = 1
  Electric Conductivity = {sigma:.17g}
End
Body Force 2
  Lorentz Velocity 1 = {velocity[0]:.17g}
  Lorentz Velocity 2 = {velocity[1]:.17g}
  Lorentz Velocity 3 = {velocity[2]:.17g}
End''')
    text=text.replace('  Fix Input Current Density = True','  Fix Input Current Density = False\n  Static Conductivity = True')
    # Diagonal scaling is also used by the upstream Faraday-disc regression.
    text=text.replace('  Linear System Preconditioning = None','  Linear System Preconditioning = Diagonal')
    text=text.replace('  Calculate Nodal Fields = True','''  Calculate Nodal Fields = False
  Calculate Elemental Fields = True
  Calculate Current Density = True
  Calculate Electric Field = True
  Calculate Joule Heating = True''')
    text=text.replace('  Save Geometry IDs = True','  Save Geometry IDs = True\n  Discontinuous Bodies = True')
    return text


def integrals(path, sigma):
    piece=ET.parse(path).getroot().find('./UnstructuredGrid/Piece')
    points=values(piece.find('./Points/DataArray')).reshape(-1,3)
    cells={a.get('Name'):values(a) for a in piece.findall('./Cells/DataArray')}
    data={a.get('Name','').casefold():a for a in piece.findall('./CellData/DataArray')}
    fields={a.get('Name','').casefold():a for a in piece.findall('./PointData/DataArray')}
    offsets=np.r_[0,cells['offsets']]
    selected=np.flatnonzero((cells['types']==10)&(values(data['geometryids'])==3))
    tetra=np.array([cells['connectivity'][offsets[i]:offsets[i+1]] for i in selected])
    if not len(tetra):raise ValueError('No finite conductor region')
    v=points[tetra];volume=np.abs(np.linalg.det(v[:,1:]-v[:,:1]))/6
    j=values(fields['current density e']).reshape(-1,3)[tetra]
    b=values(fields['magnetic flux density e']).reshape(-1,3)[tetra]
    if not np.isfinite(j).all() or not np.isfinite(b).all():raise ValueError('Non-finite current or flux')
    # Average of products of linear fields on a tetrahedron, no RMS factor in DC.
    j2=((j.sum(axis=1)**2).sum(axis=1)+(j*j).sum(axis=(1,2)))/20
    force_average=(np.cross(j.sum(axis=1),b.sum(axis=1))+np.cross(j,b).sum(axis=1))/20
    return float(volume@j2/sigma),np.sum(volume[:,None]*force_average,axis=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['gmsh','elmer','elmergrid','work']:
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--velocity',type=float,nargs=3,default=[0.01,0,0])
    parser.add_argument('--conductivity',type=float,default=25e6)
    parser.add_argument('--mesh',type=float,default=0.0008)
    parser.add_argument('--gap-mesh',type=float,default=0.0003)
    parser.add_argument('--air-radius',type=float,default=0.03)
    parser.add_argument('--oracle',type=Path,required=True)
    args=parser.parse_args()
    velocity=np.asarray(args.velocity)
    rm=MU0*args.conductivity*np.linalg.norm(velocity)*0.012
    if not np.isfinite(rm) or not np.isfinite(args.conductivity) or rm>0.01 or args.conductivity<=0 or np.linalg.norm(velocity)==0:
        parser.error('require nonzero velocity, positive conductivity and finite magnetic Reynolds number <=0.01')
    if not (0<args.gap_mesh<=args.mesh<args.air_radius and args.air_radius>0.015):
        parser.error('invalid solid/gap mesh or air domain')
    oracle=json.loads(args.oracle.read_text())
    if oracle.get('status')!='passed-prescribed-field-limit' or oracle.get('failures'):
        parser.error('requires a refined prescribed-field continuity oracle')
    np.testing.assert_allclose(oracle['request']['velocity'],args.velocity,atol=1e-15,rtol=0)
    np.testing.assert_allclose(oracle['request']['dimensions'],[0.012,0.012,0.001],atol=1e-15,rtol=0)
    if oracle['request']['slot']!=0 or oracle['request']['conductivity']!=args.conductivity:
        parser.error('oracle geometry/material does not match the unslotted finite plate')
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    report={'scope':__doc__,'status':'running','velocity_m_s':args.velocity,'magnetic_reynolds_number':rm,
            'request':{'mesh_m':args.mesh,'gap_mesh_m':args.gap_mesh,'air_radius_m':args.air_radius,'conductivity_s_m':args.conductivity},
            'oracle_sha256':hashlib.sha256(args.oracle.read_bytes()).hexdigest()}
    output=work/'summary.json';output.write_text(json.dumps(report,indent=2)+'\n')
    shutil.copyfile(HERE/'finite_plate.geo',work/'finite_plate.geo')
    (work/'case.sif').write_text(input_file(velocity,args.conductivity))
    run([str(args.gmsh.resolve()),'finite_plate.geo','-3','-format','msh2','-o','plate.msh','-v','4',
         '-setnumber','h',str(args.mesh),'-setnumber','gapmesh',str(args.gap_mesh),
         '-setnumber','thickness','0.001','-setnumber','radius',str(args.air_radius)],work,'mesh.log')
    report['material_volumes_m3']=validate_mesh(work/'plate.msh',0.001,args.air_radius)
    run([str(args.elmergrid.resolve()),'14','2','plate.msh','-out','mesh','-autoclean'],work,'convert.log')
    elapsed=run([str(args.elmer.resolve()),'case.sif'],work,'solve.log')
    files=list(work.glob('**/fields*.vtu'))
    assert len(files)==1,files
    power,force=integrals(files[0],args.conductivity)
    reference=oracle['runs'][-1]
    p_error=power/reference['joule_power_w']-1
    f_error=float(np.linalg.norm(force-reference['force_on_conductor_n'])/np.linalg.norm(reference['force_on_conductor_n']))
    balance=abs(power+float(force@velocity))/max(power,1e-30)
    magnet=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028))
    b=sample_vector(files[0],OBSERVATIONS,'magnetic flux density e')
    field_error=float(np.linalg.norm(b-magnet.getB(OBSERVATIONS))/np.linalg.norm(magnet.getB(OBSERVATIONS)))
    failures=[]
    if abs(p_error)>0.05:failures.append('Joule loss differs from the weak-field oracle by more than 5%')
    if f_error>0.05:failures.append('Lorentz force differs from the weak-field oracle by more than 5%')
    if balance>0.02:failures.append('Mechanical drag/Joule power balance exceeds 2%')
    if field_error>0.05:failures.append('PM field differs from Magpylib by more than 5%')
    report.update(status='failed' if failures else 'comparison-only',joule_power_w=power,force_on_conductor_n=force.tolist(),
                  oracle_power_error=p_error,oracle_force_vector_error=f_error,drag_joule_balance_error=balance,
                  magpylib_field_error=field_error,solve_seconds=elapsed,failures=failures,
                  input_sha256={p:hashlib.sha256((work/p).read_bytes()).hexdigest() for p in ['finite_plate.geo','case.sif','plate.msh','solve.log']})
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':
    main()
