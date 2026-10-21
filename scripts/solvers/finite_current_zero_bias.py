#!/usr/bin/env python3
"""Approved-geometry zero-current magnetic baseline, not coupled qualification.

The separate exact RT0 source is tied to this case but has zero amplitude here.
Copper is magnetically mu=1 and remains part of the reaction-air domain; its
geometry/current are neither clipped nor replaced by that mesh. Tests zero-field
and vacuum limits, named interfaces/volumes, tree gauge and nonlinear PM bias.
The original reversible material law is retained as a declared provisional law.
No winding inductance, motion, thermal or hardware quantities are qualified.
"""
import argparse
from copy import deepcopy
import itertools
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_copper_magnetic_overlap import rectangular_bounds
from compare_reduced_fields import completed_receipt
from ngsolve_material_motion import translated_source
from pm_current_force import array_magnetization_force
from post_project_force import sha
from solver_threads import add_thread_option, runtime_metadata, threaded_main
from source_snapshot import capture
from tree_gauge import free_dofs
from vector_material import MU0, magnetization_b, reduced_density
from volume_field_quadrature import sample


def magnetic_regions(model, material_names):
    names = [x['name'] for x in model['stack']]
    if len(names) != len(set(names)) or set(material_names) != {'air', *names}:
        raise ValueError('Material labels do not match the explicit approved model')
    for region in model['stack']:
        if not np.isfinite(region['mu_r']) or region['mu_r'] < 1:
            raise ValueError('Unsupported static material permeability')
        if region['name'] == 'housing' and region['mu_r'] != 1:
            raise ValueError('This baseline only supports an explicitly mu=1 housing')
    return [x for x in model['stack'] if x['name'] != 'housing' and x['mu_r'] > 1]


def posed_model(model, offset):
    if not np.isfinite(offset) or abs(offset) > 1e-4:
        raise ValueError('Only recorded lateral offsets within +/-100um are supported')
    result = deepcopy(model)
    for magnet in result['magnets']:
        magnet['origin_m'][0] += offset
    return result


def reaction_form(ng, space, mesh, model, source, rules):
    soft = magnetic_regions(model, mesh.GetMaterials())
    vacuum = sorted(set(mesh.GetMaterials())-{x['name'] for x in soft})
    trial = space.TrialFunction()
    form = ng.BilinearForm(space, symmetric=True)
    measure = lambda name: ng.dx(definedon=mesh.Materials(name), intrules=rules)
    form += ng.Variation(ng.InnerProduct(ng.curl(trial), ng.curl(trial))/(2*MU0)*measure('|'.join(vacuum)))
    for region in soft:
        density = reduced_density(ng, ng.curl(trial), source, region['mu_r'], region['bsat_t']).Compile()
        form += ng.Variation(density*measure(region['name']))
    return form


def material_mesh(ng, model, far, air_size, material_size):
    from netgen.occ import Box, Sphere, Pnt, OCCGeometry, Glue
    outer = Sphere(Pnt(0, 0, 0), far)
    outer.faces.name = 'outer'
    air = outer
    bodies = []
    for region in model['stack']:
        low, high = rectangular_bounds(region)
        if max(np.linalg.norm(p) for p in itertools.product(*zip(low, high))) >= far:
            raise ValueError('Material extends outside the reaction domain')
        body = Box(Pnt(*low), Pnt(*high))
        body.mat(region['name'])
        body.maxh = material_size
        body.faces.maxh = material_size
        body.faces.name = region['name']+'_interface'
        bodies.append(body)
        air = air-body
    air.mat('air')
    air.maxh = air_size
    mesh = ng.Mesh(OCCGeometry(Glue([air, *bodies])).GenerateMesh(maxh=air_size))
    mesh.Curve(2)
    return mesh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--material-work', type=Path, required=True)
    parser.add_argument('--source-work', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--mesh-work', type=Path)
    parser.add_argument('--mesh-only', action='store_true')
    parser.add_argument('--far', type=float, default=.04)
    parser.add_argument('--air-mesh', type=float, default=.01)
    parser.add_argument('--material-mesh', type=float, default=.002)
    parser.add_argument('--order', type=int, choices=[0, 1, 2], default=1)
    parser.add_argument('--formulation', choices=['vector-b', 'scalar-h'], default='vector-b')
    parser.add_argument('--scalar-order', type=int, choices=[1, 2, 3], default=2)
    parser.add_argument('--pm-offset-x', type=float, default=0., help='Explicit recorded lateral PM pose offset in metres, limited to +/-100um')
    parser.add_argument('--degree', type=int, default=8)
    parser.add_argument('--max-dofs', type=int, default=200000)
    add_thread_option(parser)
    args = parser.parse_args()
    material_work, source_work, work = [p.resolve() for p in [args.material_work, args.source_work, args.work]]
    if work.exists():
        parser.error('Preserve previous baselines')
    if not np.isfinite([args.far, args.air_mesh, args.material_mesh, args.pm_offset_x]).all() or abs(args.pm_offset_x) > 1e-4 or min(args.far, args.air_mesh, args.material_mesh) <= 0 or args.max_dofs < 1 or args.degree < 2 or args.degree % 2:
        parser.error('Positive finite mesh/resource limits and even integration degree required')
    material = json.loads((material_work/'summary.json').read_text())
    source = json.loads((source_work/'summary.json').read_text())
    for entry in [material, source]:
        completed_receipt(entry)
    if material['status'] != 'completed-approved-disjoint-material-geometry-only' or material['failures'] or source['status'] != 'passed-affine-rt0-source-export-only':
        raise ValueError('Need the approved disjoint geometry and accepted finite current export')
    if material['current_source_work'] != source['source_work']:
        raise ValueError('Current and material geometry belong to different cases')
    inputs = {str(material_work/'summary.json'): sha(material_work/'summary.json'),
              str(source_work/'summary.json'): sha(source_work/'summary.json'),
              str(source_work/'rt0-source.npz'): source['archive_sha256'],
              **material['input_hashes'], **source['input_hashes']}
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Approved physical source input changed')
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    from finite_current_scalar import scalar_form, magnetization_h
    if ng.__version__ != source['version']:
        raise ValueError('Source engine differs from magnetic baseline engine')
    base_model = material['model']
    model = posed_model(base_model, args.pm_offset_x)
    started = time.monotonic()
    work.mkdir(parents=True)
    report = {'status': 'running', 'scope': __doc__, 'version': ng.__version__, 'execution': runtime_metadata(),
              'formulation': args.formulation, 'scalar_order': args.scalar_order,
              'model': model, 'base_model': base_model, 'pm_offset_x_m': args.pm_offset_x,
              'input_hashes': inputs, 'current_a': 0., 'states': {}, 'failures': [],
              'request': {k: getattr(args, k) for k in ['far', 'air_mesh', 'material_mesh', 'order', 'degree', 'max_dofs']},
              'source_snapshots': capture(work, [Path(__file__), *[Path(__file__).with_name(name) for name in
                  ['vector_material.py', 'finite_current_scalar.py', 'ngsolve_material_motion.py', 'ngsolve_reduced.py', 'tree_gauge.py',
                   'volume_field_quadrature.py', 'pm_current_force.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        if args.mesh_work:
            origin = args.mesh_work.resolve()
            prior = json.loads((origin/'summary.json').read_text())
            completed_receipt(prior)
            if prior['status'] != 'passed-approved-material-mesh-controls-only' or prior.get('base_model', prior['model']) != base_model or prior['version'] != ng.__version__:
                raise ValueError('Imported mesh is not an accepted same-model baseline mesh')
            for key in ['far', 'air_mesh', 'material_mesh', 'order', 'degree']:
                if prior['request'][key] != getattr(args, key):
                    raise ValueError('Imported mesh changed the declared baseline controls')
            if sha(origin/'mesh.vol') != prior['mesh_sha256']:
                raise ValueError('Imported mesh changed')
            inputs[str(origin/'summary.json')] = sha(origin/'summary.json')
            inputs[str(origin/'mesh.vol')] = prior['mesh_sha256']
            mesh = ng.Mesh(str(origin/'mesh.vol'))
        else:
            mesh = material_mesh(ng, model, args.far, args.air_mesh, args.material_mesh)
        mesh.ngmesh.Save(str(work/'mesh.vol'))
        magnetic_regions(model, mesh.GetMaterials())
        boundaries = set(mesh.GetBoundaries())
        required_boundaries = {'outer', *[x['name']+'_interface' for x in model['stack']]}
        if boundaries != required_boundaries:
            raise ValueError('Missing/ambiguous named material interfaces or exterior boundary')
        volumes = {}
        for region in model['stack']:
            size = np.asarray(region['size_m'])
            exact_volume = float(np.prod(size))
            exact_area = float(2*(size[0]*size[1]+size[0]*size[2]+size[1]*size[2]))
            volume = float(ng.Integrate(ng.CoefficientFunction(1.), mesh, definedon=mesh.Materials(region['name']), order=args.degree))
            area = float(ng.Integrate(ng.CoefficientFunction(1.), mesh, ng.BND, definedon=mesh.Boundaries(region['name']+'_interface'), order=args.degree))
            error, area_error = abs(volume/exact_volume-1), abs(area/exact_area-1)
            if max(error, area_error) > .02:
                raise ValueError('Material volume/interface-area mesh control exceeds2%')
            volumes[region['name']] = dict(volume_m3=volume, interface_area_m2=area, volume_relative_error=error, area_relative_error=area_error)
        space = (ng.HCurl(mesh, order=args.order, nograds=True, dirichlet='outer') if args.formulation == 'vector-b'
                 else ng.H1(mesh, order=args.scalar_order, dirichlet='outer'))
        selected, tree_count = (free_dofs(ng, mesh, space, space) if args.formulation == 'vector-b' else (space.FreeDofs(), 0))
        free = np.asarray(selected, dtype=bool)
        report.update(mesh_sha256=sha(work/'mesh.vol'), elements=mesh.ne, dofs=space.ndof,
                      free_dofs=int(free.sum()), tree_fixed_edges=tree_count, material_mesh_controls=volumes,
                      boundaries=sorted(boundaries))
        save()
        if space.ndof > args.max_dofs or not free.any():
            raise ValueError('Declared magnetic DOF cap exceeded or no free gauged field')
        if args.mesh_only:
            for path, digest in inputs.items():
                if sha(Path(path)) != digest:
                    raise ValueError('Physical input changed during mesh controls')
            for path, entry in report['source_snapshots'].items():
                if sha(Path(path)) != entry['sha256']:
                    raise ValueError('Mesh implementation changed during controls')
            report.update(status='passed-approved-material-mesh-controls-only', seconds=time.monotonic()-started)
            save()
            return
        rules = {ng.ET.TET: ng.IntegrationRule(ng.ET.TET, args.degree)}
        position = [ng.Parameter(0.) for _ in range(3)]
        pm = translated_source(ng, model, position)
        gradients = [pm.Diff(p).Compile() for p in position]
        for label, case_model, field in [('zero_field', model, ng.CoefficientFunction((0., 0., 0.))),
                                        ('vacuum_limit', dict(model, stack=[dict(x, mu_r=1., bsat_t=None) for x in model['stack']]), pm),
                                        ('pm_zero_current_bias', model, pm)]:
            state = ng.GridFunction(space)
            residual = state.vec.CreateVector()
            form = (reaction_form if args.formulation == 'vector-b' else scalar_form)(ng, space, mesh, case_model, field, rules)
            form.Apply(state.vec, residual)
            initial = float(np.linalg.norm(residual.FV().NumPy()[free]))
            if label != 'pm_zero_current_bias':
                if initial > 1e-20 or abs(float(form.Energy(state.vec))) > 1e-20:
                    raise ValueError('Zero-source/vacuum limit creates a spurious magnetic reaction')
                perturbation = ng.GridFunction(space)
                perturbation.vec.FV().NumPy()[free] = np.random.default_rng(405).normal(size=int(free.sum()))*1e-8
                energy = float(form.Energy(perturbation.vec))
                if not np.isfinite(energy) or energy <= 0:
                    raise ValueError('Gauged zero-source/vacuum tangent lacks positive energy')
                report['states'][label] = {'zero_state_residual_norm': initial, 'random_gauged_field_energy_j': energy}
                save()
                continue
            if initial <= 0 or not np.isfinite(initial):
                raise ValueError('Expected nonzero nonlinear PM bias response is missing')
            result = NewtonMinimization(form, state, freedofs=selected, maxit=60, maxerr=1e-12,
                                        inverse='sparsecholesky', linesearch=True, printing=True)
            form.Apply(state.vec, residual)
            relative = float(np.linalg.norm(residual.FV().NumPy()[free]))/initial
            if result[0] != 0 or relative > 1e-9:
                raise ValueError('Zero-current nonlinear bias failed the original residual gate')
            source_force = np.zeros(3)
            independent = []
            moments = []
            for region in magnetic_regions(case_model, mesh.GetMaterials()):
                moment = (magnetization_b(ng, field+ng.curl(state), region['mu_r'], region['bsat_t'])
                          if args.formulation == 'vector-b' else
                          magnetization_h(ng, field/MU0-ng.grad(state), region['mu_r'], region['bsat_t'])).Compile()
                moments.append((region['name'], moment))
                for axis in range(3):
                    source_force[axis] -= float(ng.Integrate(ng.InnerProduct(moment, gradients[axis]), mesh,
                                                            definedon=mesh.Materials(region['name']), order=args.degree))
            for degree, increment in [(8, 1e-7), (10, 5e-8)]:
                force = np.zeros(3)
                for name, moment in moments:
                    points, values, weights = sample(ng, mesh, moment, name, degree)
                    force += array_magnetization_force(model['magnets'], points, values*weights[:, None], increment, 2).sum(axis=0)
                independent.append(force)
            balance = float(np.linalg.norm(source_force+independent[-1]))
            quadrature_change = float(np.linalg.norm(independent[-1]-independent[0]))
            limit = max(1e-8, .02*float(np.linalg.norm(independent[-1])))
            if max(balance, quadrature_change) > limit:
                raise ValueError('Zero-current PM/material force balance or quadrature fails unchanged2%gate')
            state.Save(str(work/'zero-current-reaction.sol'))
            report['states'][label] = dict(relative_residual=relative, newton_result=list(result),
                reduced_energy_j=float(form.Energy(state.vec)), material_source_force_n=source_force.tolist(),
                independent_pm_force_n=independent[-1].tolist(), force_balance_error_n=balance,
                force_quadrature_change_n=quadrature_change, force_limit_n=limit,
                solution_sha256=sha(work/'zero-current-reaction.sol'))
            save()
        for path, digest in inputs.items():
            if sha(Path(path)) != digest:
                raise ValueError('Baseline physical inputs changed during solve')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']:
                raise ValueError('Baseline implementation changed during solve')
        report.update(status='passed-recorded-zero-current-bias-controls-only', seconds=time.monotonic()-started)
        save()
    except BaseException as error:
        report.update(status='failed-zero-current-bias-controls', error=str(error), seconds=time.monotonic()-started)
        save()
        raise


if __name__ == '__main__':
    threaded_main(main)
