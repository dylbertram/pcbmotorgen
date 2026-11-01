#!/usr/bin/env python3
"""Compare explicit reference/pole-matched terminations without editing a design.

Prescribed-PM free-space numerical evidence only. This is not motor efficiency,
controller calibration, DRC acceptance, move power or hardware qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from audit_braid_layer_force import audit


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_matched(phases):
    angles = np.array([phases[p]['combined']['sine_offset_deg'] for p in 'ABC'])
    error = (angles - angles[0] + np.arange(3) * 120 + 180) % 360 - 180
    retained = [phases[p]['retained_amplitude_fraction'] for p in 'ABC']
    if not np.isfinite(angles).all() or not np.isfinite(retained).all():
        raise ValueError('Nonfinite winding audit')
    if max(abs(error)) > 1.0:
        raise ValueError('Matched directed phase axes differ from the A/B/C 120-degree sequence')
    if min(retained) < .99:
        raise ValueError('Matched layers do not add constructively')
    return dict(phase_offsets_deg=angles.tolist(), sequence_error_deg=error.tolist(),
                retained_amplitude_fraction=retained)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('output', type=Path, help='new exclusive evidence directory')
    parser.add_argument('--audit08', action='store_true',
                        help='also compare the prior explicit 0.8 mm / 0.2 mm / four-layer audit scenario')
    args = parser.parse_args()
    original = args.project.read_bytes()
    archive = json.loads(original)
    if archive['versions'][0]['state'].get('cad_geometry') is not None:
        parser.error('requires generated copper, not an imported design')
    config = archive['versions'][0]['state']['config']
    if config['routing_pattern'] != 'infinity-braid' or config['routing_params'].get('connection') != 2:
        parser.error('requires an explicit star infinity braid')
    args.output.mkdir()
    root = Path(__file__).resolve().parents[2]
    report = dict(scope=__doc__, status='running', project_sha256=sha(args.project),
                  audit_script_sha256=sha(Path(__file__)), cases={})
    summary = args.output / 'summary.json'

    def save():
        summary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')

    save()
    try:
        for scenario in ['current'] + (['audit08'] if args.audit08 else []):
            results = {}
            for matched in [False, True]:
                name = f'{scenario}-' + ('matched' if matched else 'reference')
                project = json.loads(original)
                c = project['versions'][0]['state']['config']
                c['routing_params']['pole_matched'] = int(matched)
                if scenario == 'audit08':
                    c.update(pcb_thickness_mm=.8, trace_width_mm=.2, num_layers=4)
                    c['routing_params']['num_strands'] = 3
                    c['drive'].update(outer_copper_oz=1., inner_copper_oz=1.)
                path = args.output / f'{name}.pmmotor'
                path.write_text(json.dumps(project))
                work = args.output / name
                environment = dict(os.environ, PCB_MOTOR_SIGNED_FORCE_MAP='1',
                                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', RAYON_NUM_THREADS='4')
                with (args.output / f'{name}.log').open('x') as log:
                    subprocess.run([sys.executable, str(root / 'scripts/solvers/check_winding_oracle.py'),
                                    '--project', str(path.resolve()), '--meshes', '20', '40',
                                    '--work', str(work.resolve())], cwd=root, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
                layers = {}
                for mesh in [20, 40]:
                    fixture = work / f'mesh-{mesh}/fixture.json'
                    layers[str(mesh)] = audit(fixture, fixture)
                    if matched:
                        validate_matched(layers[str(mesh)]['phases'])
                results['matched' if matched else 'reference'] = dict(
                    scenario_config=c, oracle_summary_sha256=sha(work / 'summary.json'), layers=layers)
                report['cases'][scenario] = results
                save()
            reference = results['reference']['layers']['40']['phases']
            matched = results['matched']['layers']['40']['phases']
            results['checks'] = validate_matched(matched)
            results['checks']['phase_amplitude_ratio_matched_to_reference'] = {
                p: matched[p]['combined']['amplitude_n_per_a'] / reference[p]['combined']['amplitude_n_per_a']
                for p in 'ABC'}
            # Physical B/C belts were explicitly relabeled in the matched option.
            # Their endpoint coordinates still have to be identical.
            raw = json.loads((args.output / f'{scenario}-reference/mesh-40/fixture.json').read_text())['routing']
            new = json.loads((args.output / f'{scenario}-matched/mesh-40/fixture.json').read_text())['routing']
            def active(routing, relabel):
                return sorted((s['layer'], relabel.get(s['net'], s['net']),
                               (s['start']['x'], s['start']['y']), (s['end']['x'], s['end']['y']))
                              for s in routing['segments'] if s['is_active'])
            if active(raw, {'B': 'C', 'C': 'B'}) != active(new, {}):
                raise ValueError('Active copper positions changed')
            results['checks']['active_copper_unchanged_except_B_C_labels'] = True
            save()
        if args.project.read_bytes() != original:
            raise ValueError('Source design changed during audit')
        report['status'] = 'passed-independent-pole-and-phase-force-checks'
        save()
    except BaseException as error:
        report.update(status='failed', error=str(error))
        save()
        raise


if __name__ == '__main__':
    main()
