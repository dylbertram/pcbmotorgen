#!/usr/bin/env python3
"""Offline finite-array magnetostatic job from a saved PMMOTOR version.

Requires an explicit rectangular stack footprint and array pose because project
files do not define finite housing edges. Copper is not excited or replaced by
invented terminals. Default BH laws are provisional model inputs, not measured
supplier data. Results require separate mesh/domain/backend checks.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import magpylib as magpy
import numpy as np

from check_finite_plate import require_elmer_nonlinear_convergence
from check_free_space import run
from check_plate2d import bh_points
from read_vtu import sample_vector, clear_vector_cache
from maxwell_stress import box_faces, force
from project_symmetry import quarter_model, quarter_geometry, mirrored_sample, validate_quarter_mesh
from mesh_stretch import stretched_geometry,physical_mesh
from mesh_controls import with_far_mesh
from magnet_mesh import with_magnet_faces
from source_snapshot import capture

HERE=Path(__file__).resolve().parent
MU0=4e-7*math.pi
# Same provisional constants as the application's material presets.
LAYERS={'fr4':(1,None),'flex_ferrite':(130,0.25),'mn_zn_ferrite':(2500,0.45),
        'ni_zn_ferrite':(500,0.35),'silicon_steel':(4000,1.8)}
HOUSINGS={'aluminum6061':(1,None),'aluminum5052':(1,None),'steel1018':(800,1.6),
          'stainless304':(1.02,None),'stainless316':(1.02,None),'stainless430':(500,1.2)}


def positive(value, name, allow_zero=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or (not allow_zero and value==0):
        raise ValueError(f'Invalid {name}')
    return float(value)


def project(source, version, footprint_mm, array_centre_mm):
    raw=Path(source).read_bytes();doc=json.loads(raw)
    if doc.get('format')!='pcbmotorgen-coil' or doc.get('format_version')!=1 or doc.get('document_type')!='motor':
        raise ValueError('Unsupported PMMOTOR format')
    if isinstance(version,bool) or not isinstance(version,int) or not 0<=version<len(doc['versions']):
        raise ValueError('Choose an existing zero-based saved version')
    state=doc['versions'][version]['state'];config=state['config']
    if config['topology']!='linear':raise ValueError('Only the linear alternating array is supported')
    count=config['magnet_count']
    if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=100:raise ValueError('Invalid magnet count')
    if len(footprint_mm)!=2 or len(array_centre_mm)!=2 or not np.isfinite(array_centre_mm).all():raise ValueError('Invalid finite footprint or pose')
    length,width=[positive(v,'footprint')*1e-3 for v in footprint_mm]
    pitch=positive(config['electrical_pitch_mm'],'electrical pitch')*0.5e-3
    size=[positive(config[k],k)*1e-3 for k in ['magnet_width_mm','magnet_cross_width_mm','magnet_height_mm']]
    if size[0]>=pitch:raise ValueError('Touching/overlapping magnets are unsupported')
    pcb=positive(config['pcb_thickness_mm'],'PCB thickness')*1e-3
    gap=positive(config['air_gap_mm'],'magnet gap')*1e-3
    br=positive(config['magnet_remanence_t'],'remanence')
    cx,cy=np.asarray(array_centre_mm)*1e-3
    magnets=[{'tag':i+2,'name':f'magnet_{i}','origin_m':[float(cx+(i-(count-1)/2)*pitch-size[0]/2),float(cy-size[1]/2),pcb+gap],
              'size_m':size,'polarization_t':[0,0,br*(-1 if i%2 else 1)]} for i in range(count)]
    solids=[];z=0.;stack=config.get('backplane') or {}
    for i,layer in enumerate(stack.get('layers',[])):
        if layer['material'] not in LAYERS:raise ValueError('Unsupported backplane material')
        mu,bsat=LAYERS[layer['material']]
        mu=positive(mu if layer.get('mu_r') is None else layer['mu_r'],'permeability')
        if mu<1:raise ValueError('Permeability below one is unsupported')
        bsat=bsat if layer.get('bsat_t') is None else positive(layer['bsat_t'],'saturation polarization')
        t=positive(layer['thickness_m'],'magnetic layer thickness');z-=t
        solids.append({'name':f'layer_{i}','material':layer['material'],'origin_m':[-length/2,-width/2,z],
                       'size_m':[length,width,t],'mu_r':mu,'bsat_t':bsat})
    housing=stack.get('housing')
    if housing:
        if housing['material'] not in HOUSINGS:raise ValueError('Unsupported housing material')
        mu,bsat=HOUSINGS[housing['material']]
        z-=positive(housing['gap_m'],'housing gap',allow_zero=True)
        t=positive(housing['thickness_m'],'housing thickness');z-=t
        solids.append({'name':'housing','material':housing['material'],'origin_m':[-length/2,-width/2,z],
                       'size_m':[length,width,t],'mu_r':mu,'bsat_t':bsat})
    for i,solid in enumerate(solids):solid['tag']=count+2+i
    return {'source_sha256':hashlib.sha256(raw).hexdigest(),'source_name':Path(source).name,'version_index':version,
            'coordinate_convention':'PCB bottom z=0, magnets above +z, stack below -z; array centred at explicit x/y pose',
            'saved_mover_position_mm_not_used':state.get('mover_position_mm'),'footprint_m':[length,width],
            'array_centre_mm':list(array_centre_mm),'pcb_thickness_m':pcb,'magnets':magnets,'stack':solids,
            'limitations':['rectangular common footprint supplied explicitly, not extracted housing CAD',
                           'no copper current, impedance, drag, motion or differential AC solve',
                           'provisional two-slope BH unless real material data are supplied separately',
                           'no mesh/domain/backend qualification from one job']}


def geometry(model, mesh, gap_mesh, radius):
    if not (0<gap_mesh<=mesh<radius):raise ValueError('Invalid mesh or air radius')
    objects=model['magnets']+model['stack']
    if not objects:raise ValueError('Empty geometry')
    for obj in objects:
        origin=np.array(obj['origin_m']);size=np.array(obj['size_m'])
        far=np.maximum(abs(origin),abs(origin+size))
        if np.linalg.norm(far)>=radius*0.9:raise ValueError('Air sphere must leave at least 10% radial clearance')
    lines=['SetFactory("OpenCASCADE");',f'Sphere(1)={{0,0,0,{radius:.17g}}};']
    ids=[]
    for obj in objects:
        tag=obj['tag'];ids.append(tag)
        data=','.join(f'{v:.17g}' for v in obj['origin_m']+obj['size_m'])
        lines.append(f'Box({tag})={{{data}}};')
    joined=','.join(str(tag) for tag in ids)
    lines.extend([f'air[]=BooleanDifference{{Volume{{1}};Delete;}}{{Volume{{{joined}}};}};','Coherence;',
                  'Physical Volume("air",1)={air[]};'])
    for obj in objects:lines.append(f'Physical Volume("{obj["name"]}",{obj["tag"]})={{{obj["tag"]}}};')
    minimum_size=min(gap_mesh,min(min(o['size_m'])/2 for o in objects))
    lines.extend(['outer[]=Boundary{Volume{air[]};};',f'skin[]=Boundary{{Volume{{{joined}}};}};',
                  'For i In {0:#skin[]-1}','  outer[]-={skin[i],-skin[i]};','EndFor',
                  'Physical Surface("outer",1001)={outer[]};','Mesh.MeshSizeFromPoints=0;',
                  'Mesh.MeshSizeFromCurvature=16;',f'Mesh.MeshSizeMin={minimum_size:.17g};',
                  f'Mesh.MeshSizeMax={radius/6:.17g};'])
    fields=[]
    for i,obj in enumerate(objects,1):
        field_id=10*i
        origin=np.array(obj['origin_m']);end=origin+obj['size_m']
        near=min(mesh,min(obj['size_m'])/2)
        lines.extend([f'Field[{field_id}]=Box;',f'Field[{field_id}].VIn={near:.17g};',f'Field[{field_id}].VOut={radius/6:.17g};'])
        for axis,name in enumerate('XYZ'):
            lines.extend([f'Field[{field_id}].{name}Min={origin[axis]-gap_mesh:.17g};',f'Field[{field_id}].{name}Max={end[axis]+gap_mesh:.17g};'])
        lines.append(f'Field[{field_id}].Thickness={mesh*2:.17g};');fields.append(field_id)
        if obj in model['stack'] and obj['mu_r']>1:
            # Resolve material interfaces without refining the entire thick
            # solid at the gap size. Thin sheets still have >=2 depth cells.
            for side,z in enumerate([origin[2],end[2]],1):
                face=field_id+side;fields.append(face)
                face_size=min(near,gap_mesh)
                lines.extend([f'Field[{face}]=Box;',f'Field[{face}].VIn={face_size:.17g};',f'Field[{face}].VOut={radius/6:.17g};'])
                for axis,name in enumerate('XY'):
                    lines.extend([f'Field[{face}].{name}Min={origin[axis]-gap_mesh:.17g};',f'Field[{face}].{name}Max={end[axis]+gap_mesh:.17g};'])
                lines.extend([f'Field[{face}].ZMin={z-gap_mesh:.17g};',f'Field[{face}].ZMax={z+gap_mesh:.17g};',
                              f'Field[{face}].Thickness={mesh:.17g};'])
    minimum=10*(len(objects)+1)+9
    lines.extend([f'Field[{minimum}]=Min;',f'Field[{minimum}].FieldsList={{{",".join(map(str,fields))}}};',
                  f'Background Field={minimum};','Mesh.MshFileVersion=2.2;'])
    return '\n'.join(lines)+'\n'


def sif(model, nonlinear):
    text=(HERE/'cuboid.sif').read_text()
    bodies=['Body 1\n  Target Bodies(1) = $ air\n  Equation = 1\n  Material = 1\nEnd',
            'Material 1\n  Relative Permeability = 1\n  Electric Conductivity = 0\nEnd']
    for obj in model['magnets']:
        tag=obj['tag']
        bodies.append(f'Body {tag}\n  Target Bodies(1) = $ {obj["name"]}\n  Equation = 1\n  Material = 1\n  Body Force = {tag}\nEnd')
        bodies.append(f'Body Force {tag}\n  Magnetization 3 = {obj["polarization_t"][2]/MU0:.17g}\nEnd')
    for obj in model['stack']:
        tag=obj['tag'];mu=obj['mu_r'] if nonlinear else 1
        bodies.append(f'Body {tag}\n  Target Bodies(1) = $ {obj["name"]}\n  Equation = 1\n  Material = {tag}\nEnd')
        material=f'Material {tag}\n  Relative Permeability = {mu:.17g}\n  Electric Conductivity = 0\n'
        if nonlinear and obj['bsat_t'] is not None:
            material+='  H-B Curve = Variable "dummy"\n    Real\n      INCLUDE HB_'+str(tag)+'\n    End\n'
        bodies.append(material+'End')
    text,count=re.subn(r'Body 1\n.*?(?=Equation 1\n)','\n'.join(bodies)+'\n',text,flags=re.S)
    if count!=1:raise ValueError('Unexpected base Whitney input')
    text=text.replace('  Nonlinear System Consistent Norm = True','''  Nonlinear System Consistent Norm = True
  Nonlinear System Max Iterations = 100
  Nonlinear System Convergence Tolerance = 1e-8
  Nonlinear System Relaxation Factor = 1
  Newton-Raphson Iteration = True''')
    text=text.replace('  Fix Input Current Density = True','  Fix Input Current Density = False')
    text=text.replace('  Linear System Preconditioning = None','  Linear System Preconditioning = Diagonal')
    return text


def getdp_input(model,element_order=2):
    """Reuse the qualified current-free formulation, with per-region material laws."""
    text=(HERE/'finite_plate.pro').read_text()
    magnets=','.join(str(o['tag']) for o in model['magnets'])
    plates=','.join(str(o['tag']) for o in model['stack'])
    domain=','.join(str(o['tag']) for o in model['magnets']+model['stack'])
    groups=f'''Group {{
  Air=Region[1]; Magnet=Region[{{{magnets}}}]; Plate=Region[{{{plates}}}];
  Domain=Region[{{1,{domain}}}]; Outer=Region[1001];
}}
'''
    functions=['Function {','  mu0=4*Pi*1e-7;','  br[Region[{Air,Plate}]]=Vector[0,0,0];',
               '  permeability[Region[{Air,Magnet}]]=mu0;']
    for obj in model['magnets']:
        functions.append(f'  br[Region[{obj["tag"]}]]=Vector[0,0,{obj["polarization_t"][2]:.17g}];')
    for obj in model['stack']:
        tag=obj['tag'];mu=obj['mu_r'];bsat=obj['bsat_t']
        if mu==1 or bsat is None:
            functions.append(f'  permeability[Region[{tag}]]=(Mode==0) ? mu0 : mu0*{mu:.17g};')
            functions.append(f'  tangentNL[Region[{tag}]]=TensorDiag[0,0,0];')
        else:
            hk=bsat/(MU0*(mu-1))
            functions.extend([f'  permeability[Region[{tag}]]=(Mode==0) ? mu0 : ((Mode==1 || Norm[$1]<={hk:.17g}) ? mu0*{mu:.17g} : mu0+{bsat:.17g}/Norm[$1]);',
                              f'  tangentNL[Region[{tag}]]=(Mode!=2 || Norm[$1]<={hk:.17g}) ? TensorDiag[0,0,0] : -{bsat:.17g}/Norm[$1]^3*SquDyadicProduct[$1];'])
    functions.append('}')
    text,count=re.subn(r'Group \{.*?(?=Constraint)',groups+'\n'.join(functions)+'\n',text,flags=re.S)
    if count!=1:raise ValueError('Unexpected base scalar-potential input')
    left=min(o['origin_m'][0] for o in model['magnets']);right=max(o['origin_m'][0]+o['size_m'][0] for o in model['magnets'])
    y=model['array_centre_mm'][1]*1e-3;z=model['pcb_thickness_m']/2
    old='Print[b,OnLine {{-0.003,0,0.0008}{0.003,0,0.0008}} {24},Format SimpleTable,File "field.txt"];'
    if text.count(old)!=1:raise ValueError('Unexpected scalar field export')
    new=f'Print[b,OnLine {{{{{left:.17g},{y:.17g},{z:.17g}}}{{{right:.17g},{y:.17g},{z:.17g}}}}} {{60}},Format SimpleTable,File "field.txt"];'
    new+='\n      Print[b,OnElementsOf Air,Format Gmsh,File "air.pos"];'
    text=text.replace(old,new)
    if element_order==1:
        text=text.replace('      {Name se; NameOfCoef pe; Function BF_Node_2E; Support Domain; Entity EdgesOf[All];}\n','')
        text=text.replace('      {NameOfCoef pe; EntityType EdgesOf; NameOfConstraint Boundary;}\n','')
    elif element_order!=2:raise ValueError('Scalar element order must be one or two')
    return text


def validate_mesh(path, model, radius):
    lines=path.read_text().splitlines();start=lines.index('$Nodes');n=int(lines[start+1])
    nodes={int(v[0]):np.array(list(map(float,v[1:]))) for v in (row.split() for row in lines[start+2:start+2+n])}
    start=lines.index('$Elements');n=int(lines[start+1]);volumes={};outer=set()
    for row in lines[start+2:start+2+n]:
        v=list(map(int,row.split()));vertices=v[3+v[2]:]
        if v[1]==4:
            a,b,c,d=[nodes[i] for i in vertices]
            volume=abs(np.linalg.det([b-a,c-a,d-a]))/6
            volumes[v[3]]=volumes.get(v[3],0)+volume
        elif v[1]==2 and v[3]==1001:outer.update(vertices)
    objects=model['magnets']+model['stack']
    if set(volumes)!={1,*[o['tag'] for o in objects]}:raise ValueError('Missing or overlapping material regions')
    for obj in objects:
        if abs(volumes[obj['tag']]/np.prod(obj['size_m'])-1)>1e-6:raise ValueError('Material volume does not match the project')
    if not outer or max(abs(np.linalg.norm(nodes[i])-radius) for i in outer)>1e-8:
        raise ValueError('Outer boundary includes a material interface or is missing')
    return volumes


def check_force_paths(runs, absolute_floor_n=1e-8):
    bare=runs['bare'].get('stack_force_by_clearance_n')
    stacked=runs['stack'].get('stack_force_by_clearance_n')
    if not stacked:return []
    if not bare or set(bare)!=set(stacked):raise ValueError('Missing closed-surface force control')
    vectors=np.array(list(stacked.values()));control=np.array(list(bare.values()))
    if vectors.shape!=(3,3) or control.shape!=(3,3) or not np.isfinite(vectors).all() or not np.isfinite(control).all():
        raise ValueError('Invalid closed-surface force vectors')
    scale=max(float(np.max(np.linalg.norm(vectors,axis=1))),absolute_floor_n)
    failures=[]
    if np.max(np.linalg.norm(control,axis=1))>max(absolute_floor_n,0.02*scale):
        failures.append('Empty-stack force floor exceeds max(10 nN, 2% of stack force)')
    if np.max(np.linalg.norm(vectors-vectors[1],axis=1))>max(absolute_floor_n,0.02*scale):
        failures.append('Closed-surface force-path sensitivity exceeds max(10 nN, 2%)')
    return failures


def getdp_nonlinear_convergence(job):
    """Read the legacy GetDP update/stopping proxy and its actual loop count.

    GetDP labels this value 'Nonlinear Residual norm', but SolveJac documents
    it as relative solution-update error. It is not an independently assembled
    ||F(x)|| certificate. New reduced-response checks use equilibrium.txt instead.
    The historical return-key name is retained for archived-report compatibility.
    """
    residual=np.loadtxt(job/'nonlinear.txt').reshape(-1,2)[-1]
    log=(job/'solve.log').read_text()
    values=re.findall(r'^\s*Info\s*:\s+(\d+) Nonlinear Residual norm\s+(\S+)',log,re.M)
    if not values or not np.isfinite(residual).all() or not 0<=residual[0]<=1e-9:
        raise ValueError('Scalar nonlinear solve did not converge')
    iteration,value=int(values[-1][0]),float(values[-1][1])
    if iteration<1 or not np.isfinite(value) or not 0<=value<=1e-9 or not np.isclose(value,residual[0],rtol=1e-6,atol=1e-15):
        raise ValueError('Nonlinear log and residual artifact do not agree')
    # GetDP 3.5.0's printed $NLIteration can be zero even after a real loop.
    return {'relative_residual':float(residual[0]),'iterations':iteration,'iteration_source':'nonlinear residual log'}


def finish_report(report, source, work, status, failures):
    """Validate immutable inputs before publishing any completed study status."""
    if status not in ['comparison-only','completed-bare-field-only-unqualified']:
        raise ValueError('Unsupported completed project status')
    failures=list(failures)
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=report['model']['source_sha256']:
        failures.append('Source project changed during the job')
    for path,entry in report.get('source_snapshots',{}).items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=entry['sha256']:
            failures.append('Source implementation or input changed during the job: '+path)
    report.update(status='failed' if failures else status,failures=failures,
                  mesh_sha256=hashlib.sha256((work/'project.msh').read_bytes()).hexdigest())
    (work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if failures:raise ValueError('\n'.join(failures))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--version',type=int,required=True)
    parser.add_argument('--footprint-mm',type=float,nargs=2,required=True,metavar=('LENGTH','WIDTH'))
    parser.add_argument('--array-centre-mm',type=float,nargs=2,required=True,metavar=('X','Y'))
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--mesh',type=float,default=0.0008)
    parser.add_argument('--gap-mesh',type=float,default=0.0001)
    parser.add_argument('--radius',type=float,default=0.06)
    parser.add_argument('--far-mesh',type=float,help='independent far-air mesh maximum; default radius/6. Hold fixed during an exterior-radius study')
    parser.add_argument('--magnet-face-mesh',type=float,help='optional independent PM-interface X/Y mesh target; restored Z target is divided by --z-stretch')
    parser.add_argument('--magnet-face-band',type=float,help='optional physical half-width of the PM refinement bands in metres; requires --magnet-face-mesh and preserves Z reach after stretching')
    parser.add_argument('--bare-only',action='store_true',help='stop after the completed free-space field control; never qualifies material force or nonlinear response')
    parser.add_argument('--force-subdivisions',type=int,default=64,help='midpoint quadrature per face direction; repeat at twice this value separately')
    parser.add_argument('--gmsh',type=Path)
    parser.add_argument('--elmer',type=Path)
    parser.add_argument('--elmergrid',type=Path)
    parser.add_argument('--getdp',type=Path)
    parser.add_argument('--element-order',type=int,choices=[1,2],default=2,help='GetDP scalar basis; all field/force gates remain unchanged')
    parser.add_argument('--relaxation',type=float,default=1.,help='GetDP Newton damping only; material law and 1e-9 residual gate stay unchanged')
    parser.add_argument('--quarter',action='store_true',help='GetDP only: verify exact x/y mirror symmetry and reconstruct full fields/force surfaces')
    parser.add_argument('--z-stretch',type=float,default=1.,help='experimental mesh construction only: stretch CAD Z, then restore mesh nodes to physical SI before either backend solves')
    parser.add_argument('--mesh-from',type=Path,help='reuse only a byte-identical geometry job mesh, after region validation')
    args=parser.parse_args()
    if not 2<=args.force_subdivisions<=512:parser.error('force subdivisions must be between 2 and 512')
    if not np.isfinite(args.relaxation) or not 0<args.relaxation<=1:parser.error('relaxation must be in (0,1]')
    if bool(args.elmer)!=bool(args.elmergrid) or (args.elmer and not args.gmsh):parser.error('solve requires gmsh, ElmerGrid and ElmerSolver')
    if args.getdp and (args.elmer or not args.gmsh):parser.error('choose GetDP with gmsh, or Elmer with gmsh/ElmerGrid')
    if args.quarter and args.elmer:parser.error('quarter symmetry is qualified for the scalar GetDP formulation only')
    if args.far_mesh is not None and (not np.isfinite(args.far_mesh) or not args.mesh<=args.far_mesh<args.radius):
        parser.error('far mesh must be finite and between the near mesh and exterior radius')
    if args.magnet_face_mesh is not None and (not np.isfinite(args.magnet_face_mesh) or not 0<args.magnet_face_mesh<=args.mesh):
        parser.error('magnet face mesh must be finite, positive and no larger than the near mesh')
    if args.magnet_face_band is not None and (args.magnet_face_mesh is None or not np.isfinite(args.magnet_face_band) or not 0<args.magnet_face_band<args.radius):
        parser.error('magnet face band requires an interface mesh target and must be positive, finite and smaller than the air radius')
    model=project(args.project,args.version,args.footprint_mm,args.array_centre_mm)
    solver_model=quarter_model(model) if args.quarter else model
    work=args.work.resolve()
    # Never turn the user source or an earlier result into a generated job.
    work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):parser.error('--work must be an empty output directory')
    if args.z_stretch==1:
        geo=(quarter_geometry if args.quarter else geometry)(solver_model,args.mesh,args.gap_mesh,args.radius)
    else:
        geo=stretched_geometry(solver_model,args.mesh,args.gap_mesh,args.radius,args.z_stretch,quarter=args.quarter)
    if args.far_mesh is not None:geo=with_far_mesh(geo,args.far_mesh)
    if args.magnet_face_mesh is not None:
        geo=with_magnet_faces(geo,solver_model,args.magnet_face_mesh,args.z_stretch,args.far_mesh if args.far_mesh is not None else args.radius/6,args.magnet_face_band)
    (work/'project.geo').write_text(geo)
    backend='elmer' if args.elmer else ('getdp' if args.getdp or args.quarter or args.z_stretch!=1 else 'elmer')
    report={'scope':__doc__,'status':'inputs-only','model':model,'mesh_m':args.mesh,'gap_mesh_m':args.gap_mesh,'air_radius_m':args.radius,'runs':{},
            'backend':backend,
            'element_order':args.element_order if backend=='getdp' else 1,
             'getdp_relaxation':args.relaxation,
             'quarter_symmetry':args.quarter,
             'z_stretch':args.z_stretch,
             'far_mesh_m':args.far_mesh if args.far_mesh is not None else args.radius/6,
              'magnet_face_mesh_m':args.magnet_face_mesh,
              'magnet_face_band_m':args.magnet_face_band,
             'bare_only':args.bare_only,
            'force_subdivisions':args.force_subdivisions,
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'base_sif_sha256':hashlib.sha256((HERE/'cuboid.sif').read_bytes()).hexdigest()}
    if args.quarter:
        report['solver_geometry_model']=solver_model
        report['symmetry_helper_sha256']=hashlib.sha256((HERE/'project_symmetry.py').read_bytes()).hexdigest()
    if args.z_stretch!=1:
        report['mesh_coordinate_transform']={'cad_z_multiplier':args.z_stretch,'physical_node_z_divisor':args.z_stretch,
            'pde_geometry_and_materials_unscaled':True,'helper_sha256':hashlib.sha256((HERE/'mesh_stretch.py').read_bytes()).hexdigest()}
    if args.far_mesh is not None:report['far_mesh_control_sha256']=hashlib.sha256((HERE/'mesh_controls.py').read_bytes()).hexdigest()
    if args.magnet_face_mesh is not None:report['magnet_mesh_control_sha256']=hashlib.sha256((HERE/'magnet_mesh.py').read_bytes()).hexdigest()
    report['source_snapshots']=capture(work,[args.project,Path(__file__),*[HERE/name for name in ['magnet_mesh.py','mesh_stretch.py','mesh_controls.py',
        'project_symmetry.py','check_free_space.py','job_status.py','check_finite_plate.py','check_plate2d.py','maxwell_stress.py','read_vtu.py','cuboid.sif']]])
    output=work/'summary.json';output.write_text(json.dumps(report,indent=2)+'\n')
    if not args.gmsh:return
    report['status']='running';output.write_text(json.dumps(report,indent=2)+'\n')
    if args.mesh_from:
        import shutil
        origin=args.mesh_from.resolve()
        if (origin/'project.geo').read_text()!=geo:raise ValueError('Cannot reuse a mesh from different geometry or mesh settings')
        shutil.copyfile(origin/'project.msh',work/'project.msh')
        if args.z_stretch!=1:shutil.copyfile(origin/'project-scaled.msh',work/'project-scaled.msh')
        report['mesh_reused_from']=str(origin)
    else:
        mesh_name='project-scaled.msh' if args.z_stretch!=1 else 'project.msh'
        run([str(args.gmsh.resolve()),'project.geo','-3','-format','msh2','-o',mesh_name,'-v','4'],work,'mesh.log')
        if args.z_stretch!=1:physical_mesh(work/'project-scaled.msh',work/'project.msh',args.z_stretch,args.radius)
    if args.z_stretch!=1:report['scaled_mesh_sha256']=hashlib.sha256((work/'project-scaled.msh').read_bytes()).hexdigest()
    report['material_volumes_m3']=validate_mesh(work/'project.msh',solver_model,args.radius)
    if args.quarter:report['symmetry_mesh_validation']=validate_quarter_mesh(work/'project.msh')
    if not args.elmer and not args.getdp:
        report['status']='mesh-only';output.write_text(json.dumps(report,indent=2)+'\n');return
    magnets=[magpy.magnet.Cuboid(dimension=o['size_m'],polarization=o['polarization_t'],position=np.array(o['origin_m'])+np.array(o['size_m'])/2) for o in model['magnets']]
    left=min(o['origin_m'][0] for o in model['magnets']);right=max(o['origin_m'][0]+o['size_m'][0] for o in model['magnets'])
    observations=np.column_stack([np.linspace(left,right,61),np.full(61,args.array_centre_mm[1]*1e-3),np.full(61,model['pcb_thickness_m']/2)])
    expected=sum(m.getB(observations) for m in magnets)
    failures=[]
    for nonlinear,name in [(False,'bare'),(True,'stack')]:
        clear_vector_cache()
        job=work/name;job.mkdir()
        if args.getdp:
            (job/'project.pro').write_text(getdp_input(solver_model,args.element_order))
            elapsed=run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-solve','SolvePM','-v','4',
                         '-setnumber','Mode',str(2 if nonlinear else 0),'-setnumber','Relaxation',str(args.relaxation),'-ksp_type','cg','-pc_type','gamg',
                         '-ksp_rtol','1e-11','-ksp_max_it','2000','-ksp_converged_reason','-ksp_error_if_not_converged'],job,'solve.log')
            if 'CONVERGED_' not in (job/'solve.log').read_text():raise ValueError('Missing scalar linear convergence')
            convergence=None
            if nonlinear:
                convergence=getdp_nonlinear_convergence(job)
            air=job/'air.pos';formulation=job/'project.pro'
            table=np.loadtxt(job/'field.txt')
            if table.shape!=(61,6) or not np.isfinite(table).all():raise ValueError('Invalid scalar field export')
            if args.quarter:
                import shutil
                shutil.copyfile(job/'field.txt',job/'field-native.txt')
                field=mirrored_sample(air,observations)
            else:
                np.testing.assert_allclose(table[:,:3],observations,atol=1e-14,rtol=0)
                field=table[:,3:]
        else:
            (job/'case.sif').write_text(sif(model,nonlinear))
            for obj in model['stack']:
                if obj['bsat_t'] is not None:
                    (job/f'HB_{obj["tag"]}').write_text('\n'.join(f'{b:.17g} {h:.17g}' for b,h in bh_points(obj['mu_r'],obj['bsat_t'],knee=True))+'\n')
            run([str(args.elmergrid.resolve()),'14','2',str(work/'project.msh'),'-out','mesh','-autoclean'],job,'convert.log')
            elapsed=run([str(args.elmer.resolve()),'case.sif'],job,'solve.log')
            convergence=require_elmer_nonlinear_convergence((job/'solve.log').read_text()) if nonlinear and any(o['bsat_t'] is not None for o in model['stack']) else None
            files=list(job.glob('**/fields*.vtu'))
            if len(files)!=1:raise ValueError('Missing or ambiguous field output')
            field=sample_vector(files[0],observations);air=files[0];formulation=job/'case.sif'
        np.savetxt(job/'field.txt',np.column_stack([observations,field]))
        result={'solve_seconds':elapsed,'nonlinear_convergence':convergence,'air_field_sha256':hashlib.sha256(air.read_bytes()).hexdigest(),
                'formulation_sha256':hashlib.sha256(formulation.read_bytes()).hexdigest()}
        if not nonlinear:
            error=float(np.linalg.norm(field-expected)/np.linalg.norm(expected));result['magpylib_vector_error']=error
            if error>0.05:failures.append('Bare array field differs from Magpylib by more than 5%')
        if model['stack']:
            bottom=min(o['origin_m'][2] for o in model['stack']);length,width=model['footprint_m']
            result['stack_force_by_clearance_n']={}
            for clearance in [0.0001,0.0002,0.0003]:
                faces=box_faces(length/2+clearance,bottom-clearance,clearance,args.force_subdivisions,halfdepth=width/2+clearance)
                reader=mirrored_sample if args.quarter else sample_vector
                fields=[reader(air,points,'magnetic flux density e') for points,_,_ in faces]
                result['stack_force_by_clearance_n'][str(clearance)]=force(faces,fields).tolist()
        report['runs'][name]=result;output.write_text(json.dumps(report,indent=2)+'\n')
        print(name,json.dumps(result),flush=True)
        if failures:
            report.update(status='failed',failures=failures)
            output.write_text(json.dumps(report,indent=2)+'\n')
            raise SystemExit('\n'.join(failures))
        if args.bare_only:
            finish_report(report,args.project,work,'completed-bare-field-only-unqualified',[])
            return
    failures.extend(check_force_paths(report['runs']))
    finish_report(report,args.project,work,'comparison-only',failures)


if __name__=='__main__':
    main()
