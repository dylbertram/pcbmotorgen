"""Create a compact, hash-bound summary of an exclusive native screening run."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(baselines, models, results, sensitivity=None):
    cases = {}
    for design in ('fader', 'star2'):
        for move in ('full-forward', 'short-forward', 'short-return'):
            name = f'{design}-{move}.json'
            baseline_path, model_path, result_path = (p / name for p in (baselines, models, results))
            baseline = json.loads(baseline_path.read_text())
            model = json.loads(model_path.read_text())
            run = json.loads(result_path.read_text())
            if len(run) != 3 or not model['omitted_losses']:
                raise ValueError('Expected three refinements and explicitly omitted losses')
            levels = []
            for r in run:
                demand = r['result']['demand']
                if demand['source_model_scope'] != 'partial_declared_scenario' or demand['source'] is None:
                    raise ValueError('Incomplete screening results cannot be represented as complete')
                levels.append(dict(input_sha256=r['input_sha256'],
                    positions=r['inputs']['move_request']['force_positions'],
                    time_step_s=demand['actual_time_step_s'], source=demand['source'],
                    physical_tracking_findings=demand['limiting_factors'],
                    source_balance_residual_j=demand['source_balance_residual_j'],
                    mechanical_balance_residual_j=demand['mechanical_balance_residual_j'],
                    accounted_loss_energy_j=demand['accounted_loss_energy_j']))
            cases[name.removesuffix('.json')] = dict(
                archive=baseline['archive'], archive_sha256=baseline['archive_sha256'],
                version=baseline['version'], baseline_sha256=sha(baseline_path),
                model_sha256=sha(model_path), native_receipt_sha256=sha(result_path),
                baseline_input_sha256=baseline['native']['input_sha256'],
                omitted_losses=model['omitted_losses'], model_reference=model['reference'],
                ripple_reference=model['ripple']['reference'], refinements=levels)
    summary = dict(schema='partial-saved-design-screening-v1',
                scope='Partial modeled demand, NOT a complete supply total, measured hardware demand, a guaranteed maximum, or achieved tracking',
                source_boundary='12 V stiff DC link, explicit regeneration sink accepted; no upstream or capacitor transient model',
                generator_sha256=sha(Path(__file__).with_name('practical_move_assumptions.py')),
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
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baselines', type=Path)
    parser.add_argument('models', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--sensitivity', type=Path)
    args = parser.parse_args()
    value = summarize(args.baselines, args.models, args.results, args.sensitivity)
    with args.output.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
