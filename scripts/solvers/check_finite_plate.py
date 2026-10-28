#!/usr/bin/env python3
"""Finite 12 x 12 mm plate below one 5 x 5 x 3 mm PM, offline diagnostic.

This tests finite magnet depth and normal-face saturation, not induced currents.
The bare, linear and nonlinear jobs share a mesh. A completed single mesh is
still NOT an accepted result; mesh/domain and cross-backend checks are required.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import magpylib as magpy
import numpy as np

from check_free_space import run
from check_plate2d import bh_points
from read_vtu import sample_vector

HERE = Path(__file__).resolve().parent
OBSERVATIONS = np.column_stack([np.linspace(-0.003,0.003,25),np.zeros(25),np.full(25,0.0008)])


def require_elmer_nonlinear_convergence(log, tolerance=1e-8):
    # CalcFields reports several projection solves under a different variable;
    # those are not iterations of the nonlinear magnetic-potential problem.
    changes=re.findall(r'^ComputeChange: NS \(ITER=(\d+)\) \(NRM,RELC\): \(\s*\S+\s+(\S+)\s*\) :: mgdynamics\s*$',log,re.M)
    if not changes or not np.isfinite(float(changes[-1][1])) or not 0<=float(changes[-1][1])<=tolerance:
        raise ValueError('No nonlinear magnetic-potential convergence evidence')
    return {'iterations':int(changes[-1][0]),'relative_change':float(changes[-1][1])}


def validate_mesh(path, thickness, radius):
    lines = path.read_text().splitlines()
    start = lines.index('$Nodes')
    nodes = {int(v[0]): np.array([float(x) for x in v[1:4]])
             for v in (line.split() for line in lines[start+2:start+2+int(lines[start+1])])}
    start = lines.index('$Elements')
    volumes = {}
    outer_nodes = set()
    for line in lines[start+2:start+2+int(lines[start+1])]:
        v = [int(x) for x in line.split()]
        vertices = v[3+v[2]:]
        if v[1] == 4:
            a,b,c,d = [nodes[i] for i in vertices]
            volume = abs(np.linalg.det(np.array([b-a,c-a,d-a])))/6
            volumes[v[3]] = volumes.get(v[3],0)+volume
        elif v[1] == 2 and v[3] == 4:
            outer_nodes.update(vertices)
    assert set(volumes) == {1,2,3}, volumes
    assert abs(volumes[2]/(0.005*0.005*0.003)-1)<1e-6, volumes
    assert abs(volumes[3]/(0.012*0.012*thickness)-1)<1e-6, volumes
    assert outer_nodes, 'Missing outer boundary'
    distances = np.linalg.norm(np.array([nodes[i] for i in outer_nodes])-[0,0,0.002],axis=1)
    assert np.max(abs(distances-radius))<1e-8, 'A material interface is incorrectly tagged as the outer boundary'
    return volumes


def elmer_input(mode, mu, bsat, relaxation=1.0):
    # Reuse the already-tested Whitney setup, with checked substitutions.
    text = (HERE / "cuboid.sif").read_text()
    old = 'Body 2\n  Target Bodies(1) = 2\n  Equation = 1\n  Material = 1\n  Body Force = 1\nEnd'
    assert text.count(old) == 1
    body = old+'''\nBody 3
  Target Bodies(1) = 3
  Equation = 1
  Material = 2
End
Material 2
  Relative Permeability = '''+str(1 if mode == 0 else mu)+'''
  Electric Conductivity = 0
'''
    if mode == 2:
        body += '  H-B Curve = Variable "dummy"\n    Real\n      INCLUDE HB\n    End\n'
    text = text.replace(old,body+'End')
    old = '  Nonlinear System Consistent Norm = True'
    assert text.count(old) == 1
    return text.replace(old,old+f'''
  Nonlinear System Max Iterations = 100
  Nonlinear System Convergence Tolerance = 1e-8
  Nonlinear System Relaxation Factor = {relaxation:.17g}
  Newton-Raphson Iteration = True
''')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["gmsh","work"]:
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ["getdp","elmer","elmergrid"]:
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--mesh',type=float,default=0.0008)
    parser.add_argument('--gap-mesh',type=float,default=0.0003)
    parser.add_argument('--thickness',type=float,default=0.005)
    parser.add_argument('--radius',type=float,default=0.03)
    parser.add_argument('--mu',type=float,default=130)
    parser.add_argument('--bsat',type=float,default=0.25)
    parser.add_argument('--relaxation',type=float,default=1.0)
    args=parser.parse_args()
    if bool(args.getdp)==bool(args.elmer) or (args.elmer and not args.elmergrid):
        parser.error('choose --getdp, or --elmer with --elmergrid')
    if not (0<args.gap_mesh<=args.mesh<args.radius and 0<args.thickness<args.radius/2 and args.mu>1 and args.bsat>0 and 0<args.relaxation<=1):
        parser.error('invalid geometry, mesh or material parameters')
    work=args.work.resolve()
    work.mkdir(parents=True,exist_ok=True)
    request={key:value for key,value in vars(args).items() if not isinstance(value,Path)}
    request['backend']='getdp' if args.getdp else 'elmer'
    report={'scope':__doc__,'status':'running','request':request,'runs':{}}
    (work/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.copyfile(HERE/'finite_plate.geo',work/'finite_plate.geo')
    run([str(args.gmsh.resolve()),'finite_plate.geo','-3','-format','msh2','-o','plate.msh',
         '-setnumber','h',str(args.mesh),'-setnumber','gapmesh',str(args.gap_mesh),
         '-setnumber','thickness',str(args.thickness),'-setnumber','radius',str(args.radius),'-v','4'],work,'mesh.log')
    # Assert material membership and exact CAD volumes before any solve.
    report['material_volumes_m3'] = validate_mesh(work/'plate.msh', args.thickness, args.radius)
    report['mesh_sha256']=hashlib.sha256((work/'plate.msh').read_bytes()).hexdigest()
    failures=[]
    for mode,name in enumerate(['bare','linear','nonlinear']):
        job=work/name
        job.mkdir(exist_ok=True)
        shutil.copyfile(work/'plate.msh',job/'plate.msh')
        (job/'request.json').write_text(json.dumps(dict(request,mode=mode),indent=2)+'\n')
        if args.getdp:
            shutil.copyfile(HERE/'finite_plate.pro',job/'finite_plate.pro')
            elapsed=run([str(args.getdp.resolve()),'finite_plate.pro','-msh','plate.msh','-solve','SolvePM','-v','4',
                '-setnumber','Mu',str(args.mu),'-setnumber','Bsat',str(args.bsat),'-setnumber','Mode',str(mode),
                '-setnumber','Relaxation',str(args.relaxation),
                '-ksp_type','cg','-pc_type','gamg','-ksp_rtol','1e-11','-ksp_max_it','2000',
                '-ksp_converged_reason','-ksp_error_if_not_converged'],job,'solve.log')
            assert 'CONVERGED_' in (job/'solve.log').read_text()
            if mode==2:
                residual=np.loadtxt(job/'nonlinear.txt').reshape(-1,2)[-1]
                assert np.isfinite(residual).all() and 0<=residual[0]<=1e-9, residual
            table=np.loadtxt(job/'field.txt')
            inputs=['finite_plate.pro','plate.msh','request.json']
        else:
            (job/'case.sif').write_text(elmer_input(mode,args.mu,args.bsat,args.relaxation))
            (job/'HB').write_text('\n'.join(f'{b:.17g} {h:.17g}' for b,h in bh_points(args.mu,args.bsat,knee=True))+'\n')
            run([str(args.elmergrid.resolve()),'14','2','plate.msh','-out','mesh','-autoclean'],job,'convert.log')
            elapsed=run([str(args.elmer.resolve()),'case.sif'],job,'solve.log')
            if mode==2:
                log=(job/'solve.log').read_text()
                require_elmer_nonlinear_convergence(log)
            files=list(job.glob('**/fields*.vtu'))
            assert len(files)==1,files
            table=np.column_stack([OBSERVATIONS,sample_vector(files[0],OBSERVATIONS)])
            np.savetxt(job/'field.txt',table)
            inputs=['case.sif','HB','plate.msh','request.json']
        assert table.shape==(25,6) and np.isfinite(table).all()
        np.testing.assert_allclose(table[:,:3],OBSERVATIONS,atol=1e-14,rtol=0)
        result={'solve_seconds':elapsed,'centre_bz_t':float(table[12,5]),
                'input_sha256':{p:hashlib.sha256((job/p).read_bytes()).hexdigest() for p in inputs}}
        if mode==0:
            magnet=magpy.magnet.Cuboid(dimension=(0.005,0.005,0.003),polarization=(0,0,1.34),position=(0,0,0.0028))
            expected=magnet.getB(OBSERVATIONS)
            error=float(np.linalg.norm(table[:,3:]-expected)/np.linalg.norm(expected))
            result['magpylib_vector_error']=error
            if error>0.05: failures.append(f'Bare field error {error:.2%} exceeds 5%')
        else:
            result['centre_gain']=result['centre_bz_t']/report['runs']['bare']['centre_bz_t']
        report['runs'][name]=result
        print(name,json.dumps(result),flush=True)
        (work/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    report['failures']=failures
    report['status']='failed' if failures else 'comparison-only'
    (work/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    if failures: raise SystemExit('\n'.join(failures))
    print('Completed finite-geometry diagnostic. Refinement, force and current-closure gates remain unvalidated.')


if __name__=='__main__':
    main()
