#!/usr/bin/env python3
"""Nonlinear finite ferrite and conductive housing under translating PMs.

Full vector B-energy, automatic material tangent, coupled charge potential and
reaction-A history. The energy ledger includes source-position work on the
magnetized material, not only current work/Joule heat. Provisional reversible
two-slope laws, fixed-remanence PMs, no winding/hysteresis/hardware qualification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from ngsolve_housing_motion import profile,source_electric,cross
from ngsolve_reduced import source_coefficient
from post_project_force import sha
from post_reduced_force import case_field
from reduced_inputs import validate_reduced_inputs
from reduced_potential import source_field
from solver_threads import add_thread_option,runtime_metadata,threaded_main
from source_snapshot import capture
from tree_gauge import free_dofs
from vector_material import reduced_density,magnetization_b,MU0


def midpoint_arrays(midpoint,previous,a_dofs,dt):
    """Stable midpoint update: subtract states before scaling the derivative.

    NGSolve's lazy vector expression can fuse two scaled equal states and leave
    an FMA residual. An exactly static material bias must give exactly zero E.
    """
    midpoint=np.asarray(midpoint);previous=np.asarray(previous)
    if midpoint.shape!=previous.shape or midpoint.ndim!=1 or not 0<a_dofs<=len(previous) or dt<=0:
        raise ValueError('Invalid midpoint field arrays')
    difference=midpoint[:a_dofs]-previous[:a_dofs]
    following=np.zeros_like(previous);derivative=np.zeros_like(previous)
    following[:a_dofs]=previous[:a_dofs]+2*difference
    derivative[:a_dofs]=(2/dt)*difference
    return following,derivative


def material_mesh(ng,model,near,fer_near,far,air_mesh):
    from netgen.occ import Box,Sphere,Pnt,OCCGeometry,Glue
    bodies=[]
    for layer in model['stack']:
        if layer['name']!='housing' and layer['mu_r']==1:continue
        lo=np.array(layer['origin_m']);hi=lo+layer['size_m']
        body=Box(Pnt(*lo),Pnt(*hi));body.mat('conductor' if layer['name']=='housing' else layer['name'])
        size=near if layer['name']=='housing' else fer_near
        body.maxh=size;body.faces.maxh=size;body.faces.name='interface';bodies.append(body)
    outer=Sphere(Pnt(0,0,0),far);outer.faces.name='outer';air=outer
    for body in bodies:air=air-body
    air.mat('air');air.maxh=air_mesh
    mesh=ng.Mesh(OCCGeometry(Glue([air,*bodies])).GenerateMesh(maxh=air_mesh));mesh.Curve(2)
    return mesh


def translated_source(ng,model,coordinates):
    moving={'magnets':[dict(m,origin_m=[value+coordinates[i] for i,value in enumerate(m['origin_m'])]) for m in model['magnets']]}
    return source_coefficient(ng,moving).Compile()


def magnetic_form(ng,space,mesh,model,bsource,rules):
    trial=space.TrialFunction();a=trial[0] if isinstance(trial,(list,tuple)) else trial
    # Compound ProxyFunction sequences are tuples in the current pinned API.
    if isinstance(a,(list,tuple)):a=a[0]
    form=ng.BilinearForm(space,symmetric=True)
    measure=lambda name:ng.dx(definedon=mesh.Materials(name),intrules=rules)
    form+=ng.Variation((ng.InnerProduct(ng.curl(a),ng.curl(a))/(2*MU0))*measure('air|conductor'))
    for material in model['stack']:
        if material['name']=='housing' or material['mu_r']==1:continue
        density=reduced_density(ng,ng.curl(a),bsource,material['mu_r'],material['bsat_t']).Compile()
        form+=ng.Variation(density*measure(material['name']))
    return form


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--sigma',type=float,required=True);parser.add_argument('--speed',type=float,default=20.)
    parser.add_argument('--span',type=float,default=.024);parser.add_argument('--start-x',type=float)
    parser.add_argument('--steps',type=int,default=96);parser.add_argument('--mesh',type=float,default=.002)
    parser.add_argument('--fer-mesh',type=float,default=.002);parser.add_argument('--far',type=float,default=.04)
    parser.add_argument('--air-mesh',type=float,default=.01);parser.add_argument('--order',type=int,choices=[0,1,2],default=2)
    parser.add_argument('--bonus-order',type=int,default=4);parser.add_argument('--max-dofs',type=int,default=500000)
    parser.add_argument('--save-every',type=int,default=12);parser.add_argument('--mesh-only',action='store_true')
    parser.add_argument('--static-only',action='store_true');add_thread_option(parser)
    parser.add_argument('--mesh-work',type=Path,help='reuse an immutable completed full-domain material mesh and equilibrium as an initial guess')
    parser.add_argument('--mesh-controls',type=Path,help='optional completed static exterior-field/force controls for the imported mesh')
    parser.add_argument('--cache-source',action='store_true',help='exact PM values at material integration points, updated every prescribed midpoint')
    parser.add_argument('--reuse-newton-factor',action='store_true',help='checked current-Jacobian CG with reusable sparse-factor preconditioner')
    args=parser.parse_args();origin=args.source_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous coupled material trials')
    if not np.isfinite([args.sigma,args.mesh,args.fer_mesh,args.far,args.air_mesh]).all() or min(args.sigma,args.mesh,args.fer_mesh,args.far,args.air_mesh)<=0 or args.max_dofs<1 or args.save_every<1:
        parser.error('Invalid physical, mesh or resource controls')
    start,duration,dt=profile(args.speed,args.span,args.steps,args.start_x)
    source=json.loads((origin/'summary.json').read_text());case_field(origin,source,'bare');validate_reduced_inputs(origin,source)
    model=source['model'];soft=[m for m in model['stack'] if m['mu_r']>1]
    housing=[m for m in model['stack'] if m['name']=='housing']
    if not soft or len(housing)!=1 or housing[0]['mu_r']!=1:parser.error('Need soft material and a single nonmagnetic housing')
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    imported=None;imported_hash=None
    if args.mesh_work:
        from compare_reduced_fields import completed_receipt
        args.mesh_work=args.mesh_work.resolve();imported=json.loads((args.mesh_work/'summary.json').read_text());completed_receipt(imported)
        if imported['status'] not in ['completed-coupled-material-static-only','completed-nonlinear-ferrite-housing-motion-unqualified'] or imported['failures'] or imported['model']!=model or imported['version']!=ng.__version__:
            raise ValueError('Imported material mesh must be a completed same-model/same-engine full-domain job')
        if sha(args.mesh_work/'mesh.vol')!=imported['mesh_sha256'] or sha(args.mesh_work/'initial-reaction.sol')!=imported['initial_solution_sha256']:
            raise ValueError('Imported material mesh or initial equilibrium changed')
        if imported['request']['order']!=args.order:raise ValueError('Imported initial guess requires the same reaction-A order')
        for key in ['mesh','fer_mesh','far','air_mesh']:setattr(args,key,imported['request'][key])
        imported_hash=sha(args.mesh_work/'summary.json')
        if args.mesh_controls:
            controls=json.loads(args.mesh_controls.read_text());completed_receipt(controls)
            if controls['status']!='passed-exterior-source-field-and-force-static-controls-only' or controls['failures'] or controls['input_hashes'].get(str(args.mesh_work/'summary.json'))!=imported_hash:
                raise ValueError('Imported mesh controls do not belong to this mesh or are unaccepted')
    elif args.mesh_controls:raise ValueError('Mesh controls require an imported completed mesh')
    work.mkdir(parents=True);snapshots=capture(work,[Path(__file__),*[Path(__file__).with_name(name) for name in
         ['vector_material.py','ngsolve_reduced.py','ngsolve_housing_motion.py','tree_gauge.py','solver_threads.py','quadrature_source.py','newton_factor.py']]])
    report={'status':'running','scope':__doc__,'version':ng.__version__,'execution':runtime_metadata(),
        'request':{key:value for key,value in vars(args).items() if key not in ['source_work','work','threads','mesh_work','mesh_controls','cache_source','reuse_newton_factor']},
        'source_assembly':'exact material-quadrature values updated at every midpoint' if args.cache_source else 'analytical particular field directly in nonlinear forms',
        'newton_linear_solver':'checked full-Jacobian CG / fixed vacuum-reference factor preconditioner' if args.reuse_newton_factor else 'fresh sparse Cholesky',
        'model':model,'source_summary_sha256':sha(origin/'summary.json'),'source_snapshots':snapshots,
        'profile':{'start_offset_m':start,'end_offset_m':start+args.speed*duration,'dt_s':dt,'duration_s':duration},
        'material_law':'full isotropic vector two-slope energy, saturation polarization not a hard total-B clamp',
        'potential_variable':'chi=(dt/2)*electric potential, one scalar reference only','steps':[],'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    if imported:
        report['imported_mesh']={'work':str(args.mesh_work),'summary_sha256':imported_hash,'request':imported['request'],
            'initial_guess_sha256':imported['initial_solution_sha256'],'scope':'Initial guess only; re-solve/check at the requested start pose. Static exterior controls do not qualify motion.'}
        if args.mesh_controls:report['imported_mesh']['static_controls']={'path':str(args.mesh_controls.resolve()),'sha256':sha(args.mesh_controls)}
    path=work/'summary.json'
    def save():path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    def unchanged():
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Coupled material implementation changed')
        if sha(origin/'summary.json')!=report['source_summary_sha256']:raise ValueError('Original material/source changed')
        if imported and (sha(args.mesh_work/'summary.json')!=imported_hash or sha(args.mesh_work/'mesh.vol')!=imported['mesh_sha256'] or sha(args.mesh_work/'initial-reaction.sol')!=imported['initial_solution_sha256']):
            raise ValueError('Imported mesh source or seed changed')
    save();started=time.monotonic()
    try:
        if imported:
            shutil.copy2(args.mesh_work/'mesh.vol',work/'mesh.vol');mesh=ng.Mesh(str(work/'mesh.vol'))
            if sha(work/'mesh.vol')!=imported['mesh_sha256']:raise ValueError('Imported mesh changed while copied')
        else:
            mesh=material_mesh(ng,model,args.mesh,args.fer_mesh,args.far,args.air_mesh);mesh.ngmesh.Save(str(work/'mesh.vol'))
        report.update(mesh_sha256=sha(work/'mesh.vol'),mesh_elements=mesh.ne,mesh_vertices=mesh.nv,mesh_materials=list(mesh.GetMaterials()))
        if args.mesh_only:
            unchanged();report.update(status='completed-coupled-material-mesh-only',seconds=time.monotonic()-started);save();return
        a_space=ng.HCurl(mesh,order=args.order,nograds=True,dirichlet='outer')
        p_space=ng.Compress(ng.H1(mesh,order=max(2,args.order+1),definedon=mesh.Materials('conductor')))
        fes=a_space*p_space
        report.update(dofs=fes.ndof,a_dofs=a_space.ndof,potential_dofs=p_space.ndof);save()
        if fes.ndof>args.max_dofs:raise ValueError('Declared dof/resource cap exceeded before matrix assembly')
        selected,tree_count=free_dofs(ng,mesh,fes,a_space);static_free,_=free_dofs(ng,mesh,a_space,a_space)
        reference=next(d for vertex in mesh.vertices for d in p_space.GetDofNrs(ng.NodeId(ng.VERTEX,vertex.nr)) if d>=0)
        selected[a_space.ndof+reference]=False;free=np.array(selected,dtype=bool)
        rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,2*(args.order+1)+args.bonus_order)}
        dc=ng.dx(definedon=mesh.Materials('conductor'),intrules=rules)
        position=[ng.Parameter(start),ng.Parameter(0.),ng.Parameter(0.)];bsource=translated_source(ng,model,position)
        gradients=[bsource.Diff(coordinate).Compile() for coordinate in position]
        # Material source derivatives are checked before they enter work/force.
        probe=np.array([[.003,.002,-.0001],[.007,.001,-.0001]])
        mapped=mesh(probe[:,0],probe[:,1],probe[:,2]);h=1e-7
        for i in range(3):
            original=start if i==0 else 0.
            position[i].Set(original+h);above=np.asarray(bsource(mapped)).reshape(-1,3)
            position[i].Set(original-h);below=np.asarray(bsource(mapped)).reshape(-1,3);position[i].Set(original)
            analytic=np.asarray(gradients[i](mapped)).reshape(-1,3)
            if np.linalg.norm(analytic-(above-below)/(2*h))>1e-6*max(np.linalg.norm(analytic),1e-12):
                raise ValueError('Source-position derivative does not match finite differences')
        form_source=bsource;source_storage=None;source_regions='|'.join(m['name'] for m in soft)
        if args.cache_source:
            from quadrature_source import fixed_source,update_source
            form_source,source_storage,rules,cache_info=fixed_source(ng,mesh,bsource,source_regions,2*(args.order+1)+args.bonus_order)
            report['source_cache']=dict(cache_info,maximum_relative_source_error=cache_info['relative_source_l2_error']);save()
        initial=ng.GridFunction(a_space);static=magnetic_form(ng,a_space,mesh,model,ng.CacheCF(form_source),rules)
        residual=initial.vec.CreateVector();static.Apply(initial.vec,residual)
        initial_scale=float(np.linalg.norm(residual.FV().NumPy()[np.array(static_free,dtype=bool)]))
        if imported:initial.Load(str(args.mesh_work/'initial-reaction.sol'))
        result=NewtonMinimization(static,initial,freedofs=static_free,maxit=80,maxerr=1e-12,inverse='sparsecholesky',linesearch=True,printing=True)
        static.Apply(initial.vec,residual);relative=float(np.linalg.norm(residual.FV().NumPy()[np.array(static_free,dtype=bool)]))/max(initial_scale,1e-30)
        report['initial_equilibrium']={'newton_result':list(result),'relative_residual':relative};save()
        if result[0]!=0 or relative>1e-9:raise ValueError('Initial nonlinear material equilibrium failed')
        initial.Save(str(work/'initial-reaction.sol'))
        report['initial_solution_sha256']=sha(work/'initial-reaction.sol')
        if args.static_only:
            unchanged();report.update(status='completed-coupled-material-static-only',seconds=time.monotonic()-started);save();return
        a,p=fes.TrialFunction();v,q=fes.TestFunction()
        magnetic=magnetic_form(ng,fes,mesh,model,bsource,rules)
        stepping=magnetic_form(ng,fes,mesh,model,form_source,rules)
        stepping+=ng.Variation((args.sigma/dt*ng.InnerProduct(a+ng.grad(p),a+ng.grad(p)))*dc)
        history=ng.BilinearForm(fes);history+=(2*args.sigma/dt*ng.InnerProduct(a,v+ng.grad(q)))*dc;history.Assemble()
        electric=source_electric(ng,bsource,args.speed).Compile();load=ng.LinearForm(fes)
        load+=(args.sigma*ng.InnerProduct(electric,v+ng.grad(q)))*dc
        previous=ng.GridFunction(fes);previous.vec.FV().NumPy()[:a_space.ndof]=initial.vec.FV().NumPy()
        midpoint=ng.GridFunction(fes);candidate=ng.GridFunction(fes);derivative=ng.GridFunction(fes)
        rhs=previous.vec.CreateVector();residual=previous.vec.CreateVector();direction=previous.vec.CreateVector();following=previous.vec.CreateVector()
        energy_old=float(magnetic.Energy(previous.vec));energy_initial=energy_old
        integrate_c=lambda field:ng.Integrate(field,mesh,definedon=mesh.Materials('conductor'),order=2*(args.order+1)+args.bonus_order)
        volume=float(integrate_c(ng.CoefficientFunction(1.)))
        current=args.sigma*(electric-derivative.components[0]-2/dt*ng.grad(midpoint.components[1]))
        force_current=cross(ng,current,bsource)
        current_observables=ng.CoefficientFunction(tuple([ng.InnerProduct(current,current)/args.sigma,ng.InnerProduct(current,electric)]+
            [force_current[i] for i in range(3)]+[current[i] for i in range(3)]+[args.sigma*ng.InnerProduct(electric,electric)])).Compile()
        material_observables=[]
        for material in soft:
            moment=magnetization_b(ng,bsource+ng.curl(midpoint.components[0]),material['mu_r'],material['bsat_t'])
            material_observables.append((material['name'],ng.CoefficientFunction(tuple(-ng.InnerProduct(moment,g) for g in gradients)).Compile()))
        drive_energy=0.;heat=0.;max_equation=0.;max_energy=0.;max_current=0.
        factor=None
        if args.reuse_newton_factor:
            from newton_factor import NewtonFactor
            setup=time.monotonic();reference=ng.BilinearForm(fes,symmetric=True)
            reference+=(ng.InnerProduct(ng.curl(a),ng.curl(v))/MU0)*ng.dx(intrules=rules)
            reference+=(2*args.sigma/dt*ng.InnerProduct(a+ng.grad(p),v+ng.grad(q)))*dc;reference.Assemble()
            factor=NewtonFactor(ng,reference.mat.Inverse(selected,inverse='sparsecholesky'))
            report['newton_preconditioner']={'kind':'vacuum curl-curl plus unchanged conducting mass; preconditioner only',
                'setup_seconds':time.monotonic()-setup,'material_contrast_bound':max(m['mu_r'] for m in soft),
                'scope':'Actual full material tangent is reassembled and solved each iterate. Its eigenvalues relative to this reference lie between1/mu_max and1; a rotating first-iterate tangent need not have that bound.'};save()
        for step in range(args.steps):
            mid=start+args.speed*(step+.5)*dt;position[0].Set(mid)
            if source_storage is not None:
                proof=update_source(ng,mesh,bsource,source_storage,rules,source_regions,2*(args.order+1)+args.bonus_order)
                report['source_cache']['maximum_relative_source_error']=max(report['source_cache']['maximum_relative_source_error'],proof['relative_source_l2_error'])
            load.Assemble()
            rhs.data=history.mat*previous.vec+load.vec;midpoint.vec.data=previous.vec
            scale=max(float(np.linalg.norm(rhs.FV().NumPy()[free])),initial_scale,1e-30)
            for iteration in range(40):
                stepping.Apply(midpoint.vec,residual);residual.data-=rhs
                norm=float(np.linalg.norm(residual.FV().NumPy()[free]));equation=norm/scale
                if equation<=1e-10:break
                stepping.AssembleLinearization(midpoint.vec)
                direction.data=factor.solve(stepping.mat,residual,selected) if factor else stepping.mat.Inverse(selected,inverse='sparsecholesky')*residual
                damping=1.
                for _ in range(30):
                    candidate.vec.data=midpoint.vec-damping*direction;test_residual=residual.CreateVector()
                    stepping.Apply(candidate.vec,test_residual);test_residual.data-=rhs
                    if np.linalg.norm(test_residual.FV().NumPy()[free])<norm:midpoint.vec.data=candidate.vec;break
                    damping*=.5
                else:raise ValueError('Coupled nonlinear midpoint line search failed')
            else:raise ValueError('Coupled nonlinear midpoint failed to converge')
            next_values,time_derivative=midpoint_arrays(midpoint.vec.FV().NumPy(),previous.vec.FV().NumPy(),a_space.ndof,dt)
            following.FV().NumPy()[:]=next_values;derivative.vec.FV().NumPy()[:]=time_derivative
            values=np.asarray(integrate_c(current_observables)).reshape(-1)
            loss,current_work=map(float,values[:2]);current_force=values[2:5];net=values[5:8];source_scale=float(values[8])
            material_force=np.zeros(3)
            for region,observable in material_observables:
                material_force+=np.asarray(ng.Integrate(observable,mesh,definedon=mesh.Materials(region),order=2*(args.order+1)+args.bonus_order)).reshape(3)
            work_done=current_work+args.speed*material_force[0]
            position[0].Set(start+args.speed*(step+1)*dt);energy_new=float(magnetic.Energy(following));position[0].Set(mid)
            change=energy_new-energy_old;defect=abs((work_done-loss)*dt-change)
            energy_scale=max(abs(work_done)*dt,loss*dt,abs(change),1e-30)
            # A fixed IEEE roundoff allowance is needed when a static negative
            # interaction potential is subtracted from itself at zero speed.
            # At operating steps it is orders below the unchanged 2% gate.
            roundoff=128*np.finfo(float).eps*max(abs(energy_new),abs(energy_old),1e-30)
            energy_limit=max(roundoff,.02*energy_scale)
            balance=defect/max(energy_scale,roundoff/.02,1e-30)
            net_relative=float(np.linalg.norm(net))/max(np.sqrt(max(loss,source_scale)*args.sigma*volume),1e-30)
            max_equation=max(max_equation,equation);max_energy=max(max_energy,balance);max_current=max(max_current,net_relative)
            record={'step':step,'source_offset_m':mid,'time_mid_s':(step+.5)*dt,'joule_power_w':loss,
                'current_source_work_w':current_work,'material_source_force_n':material_force.tolist(),
                'housing_source_force_n':current_force.tolist(),'mechanical_source_work_w':work_done,
                'reduced_magnetic_energy_end_j':energy_new,'relative_energy_balance':balance,'relative_equation_residual':equation,
                'energy_defect_j':defect,'energy_limit_j':energy_limit,'roundoff_allowance_j':roundoff,
                'net_current_relative_error':net_relative,'newton_iterations':iteration+1}
            report['steps'].append(record);save()
            if factor:report['newton_linear_solve_statistics']=factor.stats
            if not np.isfinite([equation,loss,work_done,energy_new,balance,net_relative]).all() or equation>1e-10 or defect>energy_limit or net_relative>1e-9 or loss<0:
                raise ValueError('Coupled nonlinear motion equation/current/energy gate failed at step '+str(step))
            heat+=loss*dt;drive_energy+=work_done*dt
            if (step+1)%args.save_every==0 or step==args.steps//2:
                name=f'midpoint-{step:05d}.sol';midpoint.Save(str(work/name));print(step,loss,material_force.tolist(),balance,flush=True)
            previous.vec.data=following;energy_old=energy_new
            if (step+1)%args.save_every==0:
                name=f'checkpoint-{step+1:05d}.sol';previous.Save(str(work/name));report['latest_checkpoint']={'file':name,'sha256':sha(work/name)}
            save()
        global_defect=abs(drive_energy-heat-(energy_old-energy_initial))
        global_scale=max(abs(drive_energy),heat,abs(energy_old-energy_initial),1e-30)
        global_roundoff=128*np.finfo(float).eps*max(abs(energy_old),abs(energy_initial),1e-30)
        report.update(initial_reduced_energy_j=energy_initial,final_reduced_energy_j=energy_old,joule_energy_j=heat,
            mechanical_source_energy_j=drive_energy,integrated_energy_balance=global_defect/max(global_scale,global_roundoff/.02),
            integrated_energy_defect_j=global_defect,integrated_energy_limit_j=max(.02*global_scale,global_roundoff),
            maximum_relative_equation_residual=max_equation,maximum_step_energy_balance=max_energy,maximum_net_current_relative_error=max_current,
            seconds=time.monotonic()-started)
        if global_defect>report['integrated_energy_limit_j']:
            raise ValueError('Integrated coupled source-work/heat/energy gate failed')
        unchanged();report['status']='completed-nonlinear-ferrite-housing-motion-unqualified'
        save()
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':threaded_main(main)
