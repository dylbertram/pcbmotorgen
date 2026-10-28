#!/usr/bin/env python3
"""Independent P1 verification of the production linear odd-harmonic model.

Not finite-housing/entry-exit or nonlinear-material qualification. Uses a
complex diffusion BVP, not the production reflection/field recursion. Retains
2% independent depth/sample refinement and5% region agreement gates.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from check_housing_motion_reference import cases as legacy_cases
from housing_spectral_diagnostic import harmonic_power
from post_project_force import sha
from source_snapshot import capture


def cases():
    result = [(name, case) for name, case in legacy_cases() if not case['sim']['backplane']['layers']]
    for material in ['aluminum6061', 'aluminum5052', 'stainless304', 'stainless316']:
        for speed in [3., -20.]:
            case = copy.deepcopy(result[0][1])
            case['speed_m_s'] = speed
            case['sim'].update(magnet_dims_m=[.0015, .005, .003], magnet_pitch_m=.006,
                               pcb_thickness_m=.0002, air_gap_m=.0001)
            case['sim']['backplane']['housing'].update(material=material, thickness_m=.005, gap_m=0.)
            result.append((material + '-narrow-' + str(speed), case))
    case = copy.deepcopy(result[0][1])
    case['sim']['backplane']['layers'] = [{'material': 'fr4', 'thickness_m': .002}]*3
    result.append(('three-fr4-spacers', case))
    return result


def reference(case, last, cells, samples):
    return np.sum([harmonic_power(case, h, cells=cells, samples=samples, cutoff=30.)
                   for h in range(1, last + 1, 2)], axis=0)


def relative(a, b):
    return float(np.max(abs(a-b)/np.maximum(abs(b), 1e-12)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    if args.work.exists(): parser.error('Preserve prior evidence')
    args.work.mkdir(parents=True)
    root = Path(__file__).resolve().parents[2]
    binary = args.binary.resolve()
    report = {'status': 'running', 'scope': __doc__, 'binary_sha256': sha(binary), 'cases': {}, 'failures': [],
              'source_snapshots': capture(args.work, [Path(__file__),
                  Path(__file__).with_name('housing_spectral_diagnostic.py'),
                  Path(__file__).with_name('check_housing_motion_reference.py'),
                  root/'crates/pcbmotorgen-simulation/src/backplane/housing_motion.rs',
                  root/'crates/pcbmotorgen-simulation/src/backplane/mod.rs'])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'): report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    start = time.monotonic()
    def save(): (args.work/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        for name, case in cases():
            path = args.work/(name+'.input.json')
            path.write_text(json.dumps(case, indent=2)+'\n')
            proc = subprocess.run([str(binary), str(path.resolve())], text=True, capture_output=True, timeout=60)
            (args.work/(name+'.stdout.json')).write_text(proc.stdout)
            (args.work/(name+'.stderr.log')).write_text(proc.stderr)
            if proc.returncode: raise ValueError(name+': unavailable binary calculation')
            result = json.loads(proc.stdout)
            if result['status'] != 'experimental': raise ValueError(name+': unavailable calculation')
            value = result['estimate']
            if value['method'] != 'linear_planar_odd_harmonics_region_joule_v2': raise ValueError('Wrong method')
            last = value['max_travel_harmonic']
            # Independently resolve the same terms, then add four further odd
            # harmonics to audit the claimed omitted-power bound empirically.
            coarse = reference(case, last, 96, 1024)
            fine = reference(case, last, 192, 1024)
            sampled = reference(case, last, 192, 2048)
            extra = sum(harmonic_power(case, h, cells=192, samples=2048, cutoff=30.)[-1]
                        for h in range(last+2, last+10, 2))
            actual = np.array([*value['layer_joule_power_w'], 0., value['housing_joule_power_w']])
            depth_change, sample_change, error = relative(coarse, fine), relative(fine, sampled), relative(actual, sampled)
            passed = bool(depth_change <= .02 and sample_change <= .02 and error <= .05
                          and extra <= value['travel_tail_bound_w'] + 1e-12
                          and value['travel_tail_bound_w'] <= .005*max(value['housing_joule_power_w'], 1e-12)
                          and value['cross_travel_tail_bound_w'] <= .005*max(value['housing_joule_power_w'], 1e-12)
                          and value['power_balance_relative_error'] <= 1e-8)
            report['cases'][name] = {'input_sha256': sha(path), 'rust': result, 'reference_regions_w': sampled.tolist(),
                'depth_relative_change': depth_change, 'sample_relative_change': sample_change,
                'maximum_region_relative_difference': error, 'next_four_odd_terms_housing_w': float(extra), 'passed': passed}
            if not passed: report['failures'].append(name)
            save()
            print(name, 'h', last, 'region error', error, 'passed', passed, flush=True)
        if sha(binary) != report['binary_sha256']: raise ValueError('Binary changed during verification')
        for path, entry in report['source_snapshots'].items():
            if sha(Path(path)) != entry['sha256']: raise ValueError('Source changed during verification')
        report.update(status='passed-independent-linear-housing-harmonics-only' if not report['failures'] else 'failed',
                      seconds=time.monotonic()-start)
        save()
        if report['failures']: raise ValueError('Independent harmonic controls failed')
    except BaseException as error:
        report.update(status='failed', error=str(error), seconds=time.monotonic()-start)
        save()
        raise


if __name__ == '__main__': main()
