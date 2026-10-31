"""Create a compact, hash-bound summary of an exclusive native screening run."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(baselines, models, results, sensitivity=None, engineering_estimate=False, builder=None, winding_sensitivity=None, designs=('fader', 'star2')):
    cases = {}
    for design in designs:
        for move in ('full-forward', 'short-forward', 'short-return'):
            name = f'{design}-{move}.json'
            baseline_path, model_path, result_path = (p / name for p in (baselines, models, results))
            baseline = json.loads(baseline_path.read_text())
            if design == 'generated4' and (baseline.get('archive_role') != 'configuration_reference_only'
                    or baseline['native']['inputs'].get('cad_geometry') is not None):
                raise ValueError('Generated audit must not reuse or claim saved imported copper')
            model = json.loads(model_path.read_text())
            run = json.loads(result_path.read_text())
            if len(run) != 3 or not model['omitted_losses']:
                raise ValueError('Expected three refinements and explicitly omitted losses')
            levels = []
            previous = None
            for r in run:
                demand = r['result']['demand']
                expected_scope = 'engineering_estimate' if engineering_estimate else 'partial_declared_scenario'
                if demand['source_model_scope'] != expected_scope or demand['source'] is None:
                    raise ValueError('Incomplete screening results cannot be represented as complete')
                actual = r['inputs']
                expected = copy.deepcopy(baseline['native']['inputs'])
                expected['move_request']['loss_model'] = model
                expected['move_request']['force_positions'] = actual['move_request']['force_positions']
                expected['move_request']['profile']['time_step_s'] = actual['move_request']['profile']['time_step_s']
                if actual != expected or demand['electrical']['loss_model'] != model:
                    raise ValueError('Native inputs or model snapshot do not match the baseline and declaration')
                source = demand['source']
                loss = demand['accounted_loss_energy_j']
                if not all(math.isfinite(v) for v in (*source.values(), loss, demand['source_balance_residual_j'], demand['mechanical_balance_residual_j'])):
                    raise ValueError('Nonfinite source or balance result')
                if source['drawn_energy_j'] < 0 or source['returned_energy_j'] < 0 or abs(source['drawn_energy_j'] - source['returned_energy_j'] - source['net_energy_j']) >= 1e-9 * max(abs(source['net_energy_j']), 1):
                    raise ValueError('Drawn / returned / net energy split failed')
                if abs(demand['source_balance_residual_j']) >= 1e-6 * max(loss, 1e-6) or abs(demand['mechanical_balance_residual_j']) >= 1e-8:
                    raise ValueError('Native energy balance failed')
                if previous:
                    for key in ('net_energy_j', 'sampled_positive_peak_power_w'):
                        if abs(source[key] - previous[key]) / max(abs(source[key]), 1e-9) >= 0.02:
                            raise ValueError('Native refinement did not meet the existing 2% gate')
                previous = source
                levels.append(dict(input_sha256=r['input_sha256'],
                    positions=r['inputs']['move_request']['force_positions'],
                    time_step_s=demand['actual_time_step_s'], source=demand['source'],
                    physical_tracking_findings=demand['limiting_factors'],
                    source_balance_residual_j=demand['source_balance_residual_j'],
                    mechanical_balance_residual_j=demand['mechanical_balance_residual_j'],
                    accounted_loss_energy_j=demand['accounted_loss_energy_j']))
            cases[name.removesuffix('.json')] = dict(
                archive=baseline['archive'], archive_sha256=baseline['archive_sha256'],
                archive_role=baseline.get('archive_role', 'saved_design'),
                geometry_source=baseline.get('geometry_source', 'saved_design'),
                version=baseline['version'], baseline_sha256=sha(baseline_path),
                model_sha256=sha(model_path), native_receipt_sha256=sha(result_path),
                baseline_input_sha256=baseline['native']['input_sha256'],
                omitted_losses=model['omitted_losses'], model_reference=model['reference'],
                ripple_reference=model['ripple']['reference'],
                profile=baseline['native']['inputs']['move_request']['profile'],
                pcb_thickness_m=baseline['native']['inputs'].get('config', {}).get('pcb_thickness_m'),
                scenario_overrides=baseline.get('scenario_overrides', {}),
                geometry=model['domain'].get('geometry'), refinements=levels)
    schema = 'engineering-saved-design-estimate-v1' if engineering_estimate else 'partial-saved-design-screening-v1'
    if designs == ('generated4',):
        schema = 'engineering-generated-design-estimate-v1' if engineering_estimate else 'partial-generated-design-screening-v1'
    summary = dict(schema=schema,
                scope=('Engineering estimate with named exclusions' if engineering_estimate else 'Partial modeled demand') + ', NOT a complete supply total, measured hardware demand, a guaranteed maximum, or achieved tracking',
                source_boundary='12 V stiff DC link, explicit regeneration sink accepted; no upstream or capacitor transient model',
                generator_sha256=sha(builder or Path(__file__).with_name('practical_move_assumptions.py')),
                cases=cases)
    if sensitivity:
        summary['sensitivity'] = {}
        for design in ('fader', 'star2'):
            path = sensitivity / f'{design}-full-forward.json'
            records = json.loads(path.read_text())
            if len(records) != 2 or any(r['result']['demand']['source_model_scope'] != 'partial_declared_scenario' for r in records):
                raise ValueError('Invalid sensitivity records')
            summary['sensitivity'][design] = dict(receipt_sha256=sha(path), cases=[
                dict(label=label, input_sha256=r['input_sha256'],
                     source=r['result']['demand']['source'],
                     source_balance_residual_j=r['result']['demand']['source_balance_residual_j'])
                 for label, r in zip(('lower', 'higher'), records)])
    if winding_sensitivity:
        summary['winding_ac_sensitivity'] = {}
        for design in ('fader', 'star2'):
            path = winding_sensitivity / f'{design}-full-forward.json'
            records = json.loads(path.read_text())
            if len(records) != 2 or any(r['result']['demand']['source_model_scope'] != 'engineering_estimate' for r in records):
                raise ValueError('Invalid winding sensitivity records')
            summary['winding_ac_sensitivity'][design] = dict(receipt_sha256=sha(path),
                description='Hypothetical extra AC resistance, not component data or a confidence interval',
                cases=[dict(extra_fraction_of_hot_dc_resistance=fraction, input_sha256=r['input_sha256'],
                            source=r['result']['demand']['source'],
                            source_balance_residual_j=r['result']['demand']['source_balance_residual_j'])
                       for fraction, r in zip((0.1, 1.0), records)])
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baselines', type=Path)
    parser.add_argument('models', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--sensitivity', type=Path)
    parser.add_argument('--engineering-estimate', action='store_true')
    parser.add_argument('--builder', type=Path, help='actual model builder; defaults to the Python reference')
    parser.add_argument('--winding-sensitivity', type=Path)
    parser.add_argument('--generated-braid-audit', action='store_true', help='summarize explicitly generated four-layer cases, not saved copper')
    args = parser.parse_args()
    value = summarize(args.baselines, args.models, args.results, args.sensitivity, args.engineering_estimate, args.builder, args.winding_sensitivity,
                      ('generated4',) if args.generated_braid_audit else ('fader', 'star2'))
    with args.output.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
