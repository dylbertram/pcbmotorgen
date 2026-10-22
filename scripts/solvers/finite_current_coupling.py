#!/usr/bin/env python3
"""Recorded finite-current/material static pilot, not general app qualification.

Uses the actual RT0 source at a controlled, immutable material quadrature. PMs,
copper and returns remain explicit. Material response is solved anew for each
current. Independent PM-face kernels check PM/material and PM/current force.
No differential inductance, motion, temperature, fitted radius or hardware claim.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import time

import numpy as np

from compare_reduced_fields import completed_receipt
from finite_current_quadrature import check_rules, material_layout, source_components, weighted_rule_values
from finite_current_zero_bias import magnetic_regions, reaction_form, posed_model
from finite_current_pose_inputs import pose_forces
from finite_current_scalar import scalar_form, magnetization_h
from ngsolve_material_motion import translated_source
from pm_current_force import array_magnetization_force
from post_project_force import sha
from solver_threads import add_thread_option, runtime_metadata, threaded_main
from source_snapshot import capture
from tree_gauge import free_dofs
from vector_material import MU0, magnetization_b

CACHE_UNIT = 'tesla per loop ampere, divided by the recorded1V-loop current without fitting'


def validate_cache(report):
    if report.get('status') != 'passed-finite-source-material-quadrature-only' or report.get('failures'):
        raise ValueError('Whole accepted finite-source material cache required')
    if report.get('unit') != CACHE_UNIT or report.get('evaluated_points') != report.get('total_material_points') or report.get('evaluated_points', 0) <= 0:
        raise ValueError('Incomplete cache or ambiguous source-current units')
    values = [report.get('maximum_pointwise_opening_relative_change'),
              report.get('maximum_direct_reference_relative_difference'),
              report.get('storage', {}).get('maximum_relative_storage_error')]
    if any(v is None or not np.isfinite(v) or v < 0 for v in values) or any(v > limit for v, limit in zip(values, [.02, .05, 1e-13])):
        raise ValueError('Finite-source cache accuracy/storage controls failed')


def control_model(model, mode):
    result = deepcopy(model)
    if mode not in ['nonlinear', 'linear', 'vacuum']:
        raise ValueError('Unsupported material control mode')
    if mode != 'nonlinear':
        for region in result['stack']:
            region['bsat_t'] = None
            if mode == 'vacuum':
                region['mu_r'] = 1.
    return result


def current_pairs(currents):
    if not currents or not np.isfinite(currents).all() or len(set(currents)) != len(currents) or 0. not in currents:
        raise ValueError('Explicit finite unique current states including zero required')
    return sorted({abs(x) for x in currents if x > 0 and -x in currents})


def cache_mesh_path(cache, bias, bias_work=None, requested_model=None):
    path = str(Path(cache['mesh_work'])/'mesh.vol')
    # Netgen reserialization can change bytes without changing a loaded mesh.
    # Require the exact original mesh hash consumed by BOTH accepted jobs, and
    # load that original again. Do not infer identity from counts or geometry.
    digest = cache['input_hashes'].get(path)
    consumed = bias['input_hashes'].get(path) == digest
    produced = (bias_work is not None and Path(path) == Path(bias_work)/'mesh.vol'
                and digest == bias.get('mesh_sha256'))
    expected_model = cache['model'] if requested_model is None else requested_model
    if expected_model != bias['model'] or not digest or not (consumed or produced):
        raise ValueError('Current cache and zero-current bias did not consume the same immutable mesh/model')
    return Path(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-work', type=Path, required=True)
    parser.add_argument('--bias-work', type=Path, required=True)
    parser.add_argument('--bare-force', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--currents', type=float, nargs='+', default=[0., .1, -.1, .5, -.5])
    parser.add_argument('--mode', choices=['nonlinear', 'linear', 'vacuum'], default='nonlinear')
    parser.add_argument('--formulation', choices=['vector-b', 'scalar-h'], default='vector-b')
    parser.add_argument('--scalar-order', type=int, choices=[1, 2, 3], default=2)
    parser.add_argument('--vector-order', type=int, choices=[0, 1, 2])
    parser.add_argument('--pm-offset-x', type=float, default=0.)
    parser.add_argument('--pose-reference-work', type=Path)
    parser.add_argument('--max-dofs', type=int, default=200000)
    add_thread_option(parser)
    args = parser.parse_args()
    args.currents = [0. if x == 0 else x for x in args.currents]
    pairs = current_pairs(args.currents)
    cache_work, bias_work, bare_path, work = [p.resolve() for p in [args.cache_work, args.bias_work, args.bare_force, args.work]]
    if work.exists():
        parser.error('Preserve earlier current-biased pilots')
    cache = json.loads((cache_work/'summary.json').read_text())
    bias = json.loads((bias_work/'summary.json').read_text())
    bare = json.loads(bare_path.read_text())
    for entry in [cache, bias, bare]:
        completed_receipt(entry)
    validate_cache(cache)
    if bias['status'] != 'passed-recorded-zero-current-bias-controls-only' or bias['failures'] or bare['status'] != 'passed-bare-finite-dc-pm-force-only' or bare['failures']:
        raise ValueError('Accepted zero-current and independent bare force controls required')
    if bare.get('quadrature_control', {}).get('passed') is not True:
        raise ValueError('Bare-current force quadrature was not accepted')
    source_work = Path(cache['source_work'])
    source = json.loads((source_work/'summary.json').read_text())
    completed_receipt(source)
    if source['status'] != 'passed-affine-rt0-source-export-only':
        raise ValueError('Unaccepted actual finite current source')
    origin = Path(source['source_work'])
    original = json.loads((origin/'summary.json').read_text())
    requested_model = posed_model(cache['model'], args.pm_offset_x)
    if args.pm_offset_x and args.pose_reference_work is None:
        raise ValueError('Shifted PMs require their own accepted finite-current bare-force reference')
    original_mesh = cache_mesh_path(cache, bias, bias_work, requested_model)
    if bare['source_work'] != str(origin) or bare['source_summary_sha256'] != source['input_hashes'][str(origin/'summary.json')] or bare['source_solution_sha256'] != source['input_hashes'][str(origin/'dc-current-potential.sol')]:
        raise ValueError('Bare PM force belongs to a different physical winding current')
    # Reuse only an exactly matched source/pose, not a similarly named fixture.
    bound = [*original['input_hashes'], *original.get('study_bindings', {})]
    models = [Path(p) for p in bound if Path(p).name == 'summary.json' and sha(Path(p)) == bare['model_summary_sha256']]
    if len(models) != 1:
        raise ValueError('Missing immutable original PM-pose reference')
    original_model = json.loads(models[0].read_text())['model']
    if any(original_model[key] != cache['model'][key] for key in ['magnets', 'source_sha256', 'version_index']):
        raise ValueError('Bare force is not qualified for this PM geometry/pose; compute a separate matched reference')
    inputs = {str(cache_work/'summary.json'): sha(cache_work/'summary.json'),
              str(cache_work/'material-current-source.npz'): cache['cache_sha256'],
              str(bias_work/'summary.json'): sha(bias_work/'summary.json'), str(bias_work/'mesh.vol'): bias['mesh_sha256'],
              str(bare_path): sha(bare_path), str(models[0]): bare['model_summary_sha256'],
              str(source_work/'summary.json'): sha(source_work/'summary.json'),
              **source['input_hashes'], **cache['input_hashes']}
    pose_values = None
    if args.pose_reference_work:
        pose_path = args.pose_reference_work.resolve()/'summary.json'
        reference = json.loads(pose_path.read_text())
        if not reference.get('command_receipt'):
            raise ValueError('Whole successful pose-force receipt required')
        completed_receipt(reference)
        _, pose_pm, pose_copper = pose_forces(cache, bias, reference, args.pm_offset_x,
            sha(source_work/'summary.json'), source['effective_loop_current_a'])
        pose_values = pose_pm, pose_copper
        if any(path in inputs and inputs[path] != digest for path, digest in reference['input_hashes'].items()):
            raise ValueError('Bare-pose reference conflicts with immutable coupling input hashes')
        inputs.update(reference['input_hashes'])
        inputs[str(pose_path)] = sha(pose_path)
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError('Immutable coupling input changed')
    fine_key = max(bare['levels'], key=int)
    direct = bare['levels'][fine_key]
    if not all(x['passed'] for x in bare['levels'].values()):
        raise ValueError('Failed bare-source force refinement')
    loop = source['effective_loop_current_a']
    direct_pm = np.asarray(direct['pm_array_force_n'])/loop
    direct_copper = np.asarray(direct['copper_source_force_n'])/loop
    if pose_values is not None:
        direct_pm, direct_copper = pose_values
    import ngsolve as ng
    from ngsolve.nonlinearsolvers import NewtonMinimization
    if source['version'] != ng.__version__ or bias['version'] != ng.__version__:
        raise ValueError('Coupling engine differs from accepted source/bias')
    model = control_model(requested_model, args.mode)
    mesh = ng.Mesh(str(original_mesh))
    degree = cache['request']['degree']
    order = bias['request']['order'] if args.vector_order is None else args.vector_order
    space = (ng.HCurl(mesh, order=order, nograds=True, dirichlet='outer') if args.formulation == 'vector-b'
             else ng.H1(mesh, order=args.scalar_order, dirichlet='outer'))
    if space.ndof > args.max_dofs:
        raise ValueError('Coupled field DOF cap exceeded before assembly')
    selected, tree_count = (free_dofs(ng, mesh, space, space) if args.formulation == 'vector-b' else (space.FreeDofs(), 0))
    free = np.asarray(selected, dtype=bool)
    layout = material_layout(ng, mesh, cache['regions'], degree)
    with np.load(cache_work/'material-current-source.npz', allow_pickle=False) as archive:
        if not np.array_equal(archive['points_m'], layout.points) or not np.array_equal(archive['element_numbers'], layout.element_numbers):
            raise ValueError('Saved source is not at this exact mesh/rule physical point layout')
        unit_field, storage_components, storage = source_components(ng, mesh, layout, archive['field_t_per_loop_a'])
    check_rules(ng, layout, degree)
    position = [ng.Parameter(0.) for _ in range(3)]
    pm = translated_source(ng, model, position)
    gradients = [pm.Diff(p).Compile() for p in position]
    amplitude = ng.Parameter(0.)
    field = (pm+amplitude*unit_field).Compile()
    form = (reaction_form if args.formulation == 'vector-b' else scalar_form)(ng, space, mesh, model, field, layout.rules)
    state = ng.GridFunction(space)
    residual = state.vec.CreateVector()
    report = {'status': 'running', 'scope': __doc__, 'model': model, 'base_model': cache['model'], 'material_control': args.mode,
              'version': ng.__version__, 'execution': runtime_metadata(), 'input_hashes': inputs,
              'formulation': args.formulation, 'field_order': order if args.formulation == 'vector-b' else args.scalar_order,
              'pm_offset_x_m': args.pm_offset_x,
              'currents_a': args.currents, 'current_pairs_a': pairs, 'dofs': space.ndof, 'tree_fixed_edges': tree_count,
              'degree': degree, 'source_storage': storage, 'states': {}, 'incremental_balance': {}, 'failures': [],
              'scope_limits': ['Recorded actual geometry/source/pose only; no arbitrary-CAD qualification',
                  'Material law provisional; static electrical current at fixed saved resistivity, no thermal/magnetic-feedback change to J',
                  'Cached source forbidden off its exact quadrature; full force mesh/domain/quadrature/independent-formulation controls still separate',
                  'Stationary-force balance is combined winding+shield, not separately qualified body forces',
                  'No differential inductance, reversal, temperature, housing eddy loss or hardware rating'],
              'source_snapshots': capture(work, [Path(__file__), *[Path(__file__).with_name(n) for n in
                   ['finite_current_zero_bias.py', 'finite_current_pose_inputs.py', 'finite_current_scalar.py', 'ngsolve_reduced.py', 'finite_current_quadrature.py', 'ngsolve_material_motion.py',
                   'vector_material.py', 'tree_gauge.py', 'pm_current_force.py', 'volume_field_quadrature.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):
        report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    work.mkdir(parents=True, exist_ok=True)
    def save(): (work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    started = time.monotonic()
    save()
    try:
        for state_index, current in enumerate(args.currents):
            amplitude.Set(current)
            state.vec[:] = 0.
            form.Apply(state.vec, residual)
            initial = float(np.linalg.norm(residual.FV().NumPy()[free]))
            if initial:
                result = NewtonMinimization(form, state, freedofs=selected, maxit=60, maxerr=1e-12,
                                            inverse='sparsecholesky', linesearch=True, printing=True)
                form.Apply(state.vec, residual)
                relative = float(np.linalg.norm(residual.FV().NumPy()[free]))/initial
                if result[0] != 0 or not np.isfinite(relative) or relative > 1e-9:
                    raise ValueError('Finite-current nonlinear equilibrium failed original residual gate')
            else:
                result, relative = [0, 0], 0.
            material_source = np.zeros(3)
            points, weighted = [], []
            for region in magnetic_regions(model, mesh.GetMaterials()):
                moment = (magnetization_b(ng, field+ng.curl(state), region['mu_r'], region['bsat_t'])
                          if args.formulation == 'vector-b' else
                          magnetization_h(ng, field/MU0-ng.grad(state), region['mu_r'], region['bsat_t'])).Compile()
                for axis in range(3):
                    material_source[axis] -= float(ng.Integrate(ng.InnerProduct(moment, gradients[axis])*ng.dx(
                        definedon=mesh.Materials(region['name']), intrules=layout.rules), mesh))
                p, values = weighted_rule_values(ng, mesh, layout, moment, region['name'])
                points.append(p)
                weighted.append(values)
            forces = []
            for delta in [1e-7, 5e-8]:
                force = np.zeros(3) if not points else array_magnetization_force(model['magnets'], np.concatenate(points), np.concatenate(weighted), delta, 2).sum(axis=0)
                forces.append(force)
            pm_force = forces[-1]+current*direct_pm
            stationary = material_source+current*direct_copper
            balance = float(np.linalg.norm(pm_force+stationary))
            kernel_change = float(np.linalg.norm(forces[-1]-forces[0]))
            limit = max(1e-8, .02*float(np.linalg.norm(pm_force)))
            if max(balance, kernel_change) > limit:
                raise ValueError('Finite-current force balance/PM kernel derivative fails unchanged2%gate')
            filename = f'current-{state_index:03d}-{current:+.17g}.sol'
            state.Save(str(work/filename))
            report['states'][str(current)] = dict(relative_residual=relative, newton_result=list(result),
                reduced_energy_j=float(form.Energy(state.vec)), pm_array_force_n=pm_force.tolist(),
                material_pm_force_n=forces[-1].tolist(), material_source_force_n=material_source.tolist(),
                combined_stationary_force_n=stationary.tolist(), action_reaction_error_n=balance,
                pm_kernel_derivative_refinement_n=kernel_change, force_limit_n=limit,
                solution=filename, solution_sha256=sha(work/filename))
            save()
            print('current', current, 'mode', args.mode, 'PM force', pm_force.tolist(), 'balance', balance, flush=True)
        zero = report['states']['0.0']
        if args.mode == 'nonlinear':
            expected = np.asarray(bias['states']['pm_zero_current_bias']['independent_pm_force_n'])
            error = float(np.linalg.norm(np.asarray(zero['pm_array_force_n'])-expected))
            limit = max(1e-8, .02*float(np.linalg.norm(expected)))
            report['zero_current_reload_control'] = dict(difference_n=error, limit_n=limit, passed=error <= limit)
            if error > limit:
                report['failures'].append('Zero-current coupled limit differs from accepted PM-bias baseline')
        for current in args.currents:
            if current == 0:
                continue
            value = report['states'][str(current)]
            increment = np.asarray(value['pm_array_force_n'])-zero['pm_array_force_n']
            opposite = np.asarray(value['combined_stationary_force_n'])-zero['combined_stationary_force_n']
            error = float(np.linalg.norm(increment+opposite))
            limit = max(1e-8, .02*float(np.linalg.norm(increment)))
            report['incremental_balance'][str(current)] = dict(incremental_pm_force_n=increment.tolist(), imbalance_n=error, limit_n=limit, passed=error <= limit)
            if error > limit:
                report['failures'].append('Current-induced force balance fails2%increment gate at'+str(current))
        if args.mode in ['linear', 'vacuum']:
            report['linear_current_parity'] = {}
            for current in pairs:
                error = float(np.linalg.norm(np.asarray(report['states'][str(current)]['pm_array_force_n'])+report['states'][str(-current)]['pm_array_force_n']-2*np.asarray(zero['pm_array_force_n'])))
                limit = max(1e-8, 1e-8*float(np.linalg.norm(zero['pm_array_force_n'])))
                report['linear_current_parity'][str(current)] = dict(error_n=error, limit_n=limit, passed=error <= limit)
                if error > limit:
                    report['failures'].append('Linear/vacuum current superposition limit failed')
        for path, digest in inputs.items():
            if sha(Path(path)) != digest:
                raise ValueError('Physical coupling inputs changed during pilot')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']:
                raise ValueError('Coupling implementation changed during pilot')
        report.update(status=('failed' if report['failures'] else 'passed')+'-recorded-finite-current-static-pilot-only', seconds=time.monotonic()-started)
        save()
        if report['failures']:
            raise ValueError('; '.join(report['failures']))
    except BaseException as error:
        report.update(status='failed-recorded-finite-current-static-pilot-only', error=str(error), seconds=time.monotonic()-started)
        save()
        raise


if __name__ == '__main__':
    threaded_main(main)
