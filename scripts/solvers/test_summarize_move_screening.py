"""The evidence summary must reject changed snapshots and failed balances."""
import json
import tempfile
import unittest
from pathlib import Path

from summarize_move_screening import summarize


class SummaryValidationTest(unittest.TestCase):
    def test_rejects_mismatched_model_and_failed_balance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_dir, model_dir, result_dir = (root / s for s in ('baseline', 'model', 'result'))
            for path in (baseline_dir, model_dir, result_dir):
                path.mkdir()
            model = {'omitted_losses': ['not modeled'], 'reference': 'fixture',
                     'ripple': {'reference': 'fixture'}, 'domain': {}}
            initial = {'config': {'pcb_thickness_m': .0008}, 'move_request': {'loss_model': None, 'force_positions': 129,
                                        'profile': {'time_step_s': .0005}}}
            baseline = {'archive': 'fixture', 'archive_sha256': 'fixture', 'version': 1,
                        'scenario_overrides': {'pcb_thickness_m': .0008},
                        'native': {'inputs': initial, 'input_sha256': 'fixture'}}
            source = {'net_energy_j': 1.0, 'drawn_energy_j': 1.0, 'returned_energy_j': 0.0,
                      'sampled_positive_peak_power_w': 1.0}
            demand = {'source_model_scope': 'engineering_estimate', 'source': source,
                      'accounted_loss_energy_j': 1.0, 'source_balance_residual_j': 0.0,
                      'mechanical_balance_residual_j': 0.0, 'actual_time_step_s': .0005,
                      'limiting_factors': [], 'electrical': {'loss_model': model}}
            inputs = {'config': {'pcb_thickness_m': .0008}, 'move_request': {'loss_model': model, 'force_positions': 129,
                                       'profile': {'time_step_s': .0005}}}
            record = {'inputs': inputs, 'input_sha256': 'fixture', 'result': {'demand': demand}}
            for design in ('fader', 'star2'):
                for move in ('full-forward', 'short-forward', 'short-return'):
                    name = f'{design}-{move}.json'
                    for path, value in ((baseline_dir, baseline), (model_dir, model),
                                        (result_dir, [record, record, record])):
                        (path / name).write_text(json.dumps(value))
            kwargs = dict(engineering_estimate=True, builder=Path(__file__))
            summary = summarize(baseline_dir, model_dir, result_dir, **kwargs)
            self.assertEqual(len(summary['cases']), 6)
            self.assertEqual(summary['cases']['fader-full-forward']['pcb_thickness_m'], .0008)
            self.assertEqual(summary['cases']['fader-full-forward']['scenario_overrides'], {'pcb_thickness_m': .0008})
            for move in ('full-forward', 'short-forward', 'short-return'):
                name = f'generated4-{move}.json'
                generated = {**baseline, 'archive_role': 'configuration_reference_only',
                             'geometry_source': 'current_generated_braid'}
                for directory, value in ((baseline_dir, generated), (model_dir, model),
                                         (result_dir, [record, record, record])):
                    (directory / name).write_text(json.dumps(value))
            generated_summary = summarize(baseline_dir, model_dir, result_dir, designs=('generated4',), **kwargs)
            self.assertEqual(generated_summary['schema'], 'engineering-generated-design-estimate-v1')
            self.assertEqual(len(generated_summary['cases']), 3)
            generated['native']['inputs']['cad_geometry'] = {'imported': True}
            (baseline_dir / 'generated4-full-forward.json').write_text(json.dumps(generated))
            with self.assertRaisesRegex(ValueError, 'saved imported copper'):
                summarize(baseline_dir, model_dir, result_dir, designs=('generated4',), **kwargs)
            path = result_dir / 'fader-full-forward.json'
            records = json.loads(path.read_text())
            records[0]['result']['demand']['electrical']['loss_model']['reference'] = 'wrong'
            path.write_text(json.dumps(records))
            with self.assertRaisesRegex(ValueError, 'model snapshot'):
                summarize(baseline_dir, model_dir, result_dir, **kwargs)
            records[0]['result']['demand']['electrical']['loss_model'] = model
            records[0]['result']['demand']['source_balance_residual_j'] = .01
            path.write_text(json.dumps(records))
            with self.assertRaisesRegex(ValueError, 'energy balance'):
                summarize(baseline_dir, model_dir, result_dir, **kwargs)


if __name__ == '__main__':
    unittest.main()
