#!/usr/bin/env python3
"""Audit and package the 2026-10-21 experimental harmonic housing release.

Preserves previous delivery directories. Does not commit, sign, notarize,
install or launch the app. Native process-only smoke evidence is separate
from browser tests and does not establish WKWebView end-to-end behavior.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def completed(path):
    value = read(path)
    if value['status'] != 'completed' or type(value.get('exit_code')) is not int or value['exit_code'] != 0:
        raise ValueError('No whole successful receipt: ' + str(path))
    return value


def verify_unittest_inventory(text, expected):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    counts = re.findall(r'^Ran (\d+) tests? in ', text, re.MULTILINE)
    if counts != [str(expected)] or not re.search(r'\nOK\s*\Z', text):
        raise ValueError('Declared helper pass count requires a whole successful run with no skips')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['root', 'archive', 'work']: parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--browser-work', type=Path, help='Additional verified browser matrix; default is the initial100-check release')
    parser.add_argument('--browser-count', type=int, default=100)
    parser.add_argument('--browser-log', default='housing-harmonic-release-browser-v3-20261021.log')
    parser.add_argument('--build-log', default='housing-harmonic-release-native-build-v2-20261021.log')
    parser.add_argument('--regression-tag', default='v1')
    parser.add_argument('--startup-tag', default='v1')
    parser.add_argument('--helper-count', type=int, default=306)
    args = parser.parse_args()
    if args.helper_count <= 0: parser.error('Positive declared helper pass count required')
    root, archive, work = args.root.resolve(), args.archive.resolve(), args.work.resolve()
    if work.exists(): parser.error('Preserve previous delivery')
    reference_path = archive/'housing-harmonic-release-reference-v2-20261021/summary.json'
    reference = read(reference_path)
    if reference['status'] != 'passed-independent-linear-housing-harmonics-only' or reference['failures'] or len(reference['cases']) != 19:
        raise ValueError('Independent matrix incomplete')
    for path, entry in reference['source_snapshots'].items():
        if sha(path) != entry['sha256']: raise ValueError('Reference source changed')
    if sha(root/'target/debug/examples/housing_motion_dump') != reference['binary_sha256']:
        raise ValueError('Reference binary changed')
    for case in reference['cases'].values():
        if not case['passed']: raise ValueError('Reference case failed')

    browser_work = (args.browser_work or archive/'housing-harmonic-release-browser-v3-20261021').resolve()
    if args.browser_count <= 0: raise ValueError('Positive declared browser count required')
    browser_path = browser_work/'report.json'
    browser = read(browser_path)
    if browser['stats']['expected'] != args.browser_count or any(browser['stats'][k] for k in ['unexpected', 'flaky', 'skipped']):
        raise ValueError('Current-workspace browser matrix incomplete')
    browser_sources = browser_work/'source-hashes.json'
    if browser_sources.exists():
        for path, digest in read(browser_sources).items():
            if sha(root/path) != digest: raise ValueError('Verified browser source changed: '+path)
    batch = read(archive/f'housing-harmonic-release-acceptance-{args.regression_tag}-20261021/summary.json')
    if batch['status'] != 'completed' or any(c['status'] != 'completed' for c in batch['checks'].values()):
        raise ValueError('Application regressions failed')
    logs = [f'housing-harmonic-release-{name}-{args.regression_tag}-20261021.log' for name in
            ['simulation', 'desktop', 'helpers', 'frontend', 'frontend-build']]
    logs += ['housing-harmonic-release-reference-v2-20261021.log',
             args.browser_log,
             args.build_log,
             f'housing-harmonic-release-native-startup-{args.startup_tag}-20261021.log']
    labels = ['star2-generated', 'star4-imported', 'star4-imported-stainless12']
    logs += [f'housing-harmonic-release-project-{label}-20261021.log' for label in labels]
    if args.browser_count > 100:
        logs += ['workspace-keyboard-submenu-final-v1-20261021.log',
                 'workspace-scroll-retention-final-20261021.log',
                 'workspace-final-navigation-scroll-v2-20261021.log',
                 'housing-harmonic-package-verifier-selftest-20261021.log']
    receipts = {name: completed(archive/(name+'.command.json')) for name in logs}
    # A zero exit alone does not establish the declared test inventory.
    expected_counts = {
        'simulation': ['195 passed', '7 passed', '2 ignored'],
        'desktop': ['106 passed', '5 ignored'],
        'frontend': ['457 passed', '1 skipped'],
    }
    for name, markers in expected_counts.items():
        text = (archive/f'housing-harmonic-release-{name}-{args.regression_tag}-20261021.log').read_text()
        text = re.sub(r'\x1b\[[0-9;]*m', '', text)
        if any(marker not in text for marker in markers): raise ValueError('Declared test inventory not observed: '+name)
    verify_unittest_inventory((archive/f'housing-harmonic-release-helpers-{args.regression_tag}-20261021.log').read_text(), args.helper_count)
    startup = read(archive/f'housing-harmonic-release-native-startup-{args.startup_tag}-20261021.json')
    if startup['status'] != 'process-live-through-eight-second-startup-observation':
        raise ValueError('Native startup smoke failed')
    for label in labels:
        project = read(archive/f'housing-harmonic-release-project-{label}-20261021/summary.json')
        if project['status'] != 'passed-real-project-routing-housing-integration-only': raise ValueError('Project integration failed')
        for path, digest in project['input_hashes'].items():
            if sha(path) != digest: raise ValueError('Project/reference input changed')
        if project['result']['estimate']['method'] != 'linear_planar_odd_harmonics_region_joule_v2':
            raise ValueError('Real project did not use harmonic method')

    root_hashes = {}
    original = read(archive/'rebase-main-20261020T201636Z/manifest.json')
    for name, entry in original['files'].items():
        if Path(name).name == name and Path(name).suffix in ['.pmmotor', '.dxf']:
            if sha(root/name) != entry['sha256']: raise ValueError('Original root design changed')
            root_hashes[name] = entry['sha256']
    if len(root_hashes) != 5: raise ValueError('Original root-input inventory incomplete')

    app = root/'target/debug/bundle/macos/pcbmotorgen.app'
    executable = app/'Contents/MacOS/pcbmotorgen'
    build_source_path = archive/args.build_log.replace('.log', '.source.json')
    build_source = read(build_source_path) if build_source_path.exists() else None
    if build_source:
        if sha(executable) != build_source['executable_sha256']: raise ValueError('Built executable changed')
        for path, digest in build_source['source_files_sha256'].items():
            if sha(root/path) != digest: raise ValueError('Native build source changed: '+path)
    if startup.get('binary_sha256') and startup['binary_sha256'] != sha(executable):
        raise ValueError('Native startup observed a different executable')
    architecture = subprocess.check_output(['file', str(executable)], text=True).strip()
    if 'arm64' not in architecture: raise ValueError('Wrong native architecture')
    signature = subprocess.run(['codesign', '-dv', str(app)], capture_output=True, text=True)
    if 'TeamIdentifier=not set' not in signature.stderr: raise ValueError('Unexpected signing identity; review before delivery')

    work.mkdir(parents=True)
    subprocess.run(['ditto', str(app), str(work/'pcbmotorgen.app')], check=True)
    if sha(work/'pcbmotorgen.app/Contents/MacOS/pcbmotorgen') != sha(executable): raise ValueError('Copied executable differs')
    evidence = work/'evidence'
    evidence.mkdir()
    if build_source: shutil.copy2(build_source_path, evidence/build_source_path.name)
    for name in logs:
        for suffix in ['', '.command.json']: shutil.copy2(archive/(name+suffix), evidence/(name+suffix))
    for folder in ['housing-harmonic-release-reference-v2-20261021',
                   *[f'housing-harmonic-release-project-{label}-20261021' for label in labels]]:
        shutil.copytree(archive/folder, evidence/folder)
    shutil.copytree(browser_work, evidence/browser_work.name)
    shutil.copy2(archive/f'housing-harmonic-release-native-startup-{args.startup_tag}-20261021.json', evidence/'native-startup.json')
    for suffix in ['.stdout.log', '.stderr.log']:
        path = archive/(f'housing-harmonic-release-native-startup-{args.startup_tag}-20261021'+suffix)
        if path.exists(): shutil.copy2(path, evidence/path.name)

    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--short'], cwd=root, text=True)
    diff = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=root)
    (work/'source.diff').write_bytes(diff)
    (work/'source-status.txt').write_text(status)
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    paths += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z', '--',
                                     'scripts', 'app', 'crates'], cwd=root).decode().split('\0')
    paths = sorted(set(p for p in paths if p and (root/p).is_file()))
    source_hashes = {p: sha(root/p) for p in paths}
    with tarfile.open(work/'source.tar.gz', 'w:gz') as tar:
        for path in paths: tar.add(root/path, arcname=path, recursive=False)
    for path, digest in source_hashes.items():
        if sha(root/path) != digest: raise ValueError('Source changed during packaging')
    zip_path = work/'pcbmotorgen-harmonic-experimental-macos-arm64-20261021.zip'
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(work/'pcbmotorgen.app'), str(zip_path)], check=True)
    app_hashes = {str(p.relative_to(work)): sha(p) for p in (work/'pcbmotorgen.app').rglob('*') if p.is_file()}
    report = {
        'status': 'verified-experimental-harmonic-housing-release', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'git_head': head, 'source_state': 'Uncommitted implementation and reference work atop HEAD; no commit/push performed',
        'source_files_sha256': source_hashes, 'source_archive_sha256': sha(work/'source.tar.gz'),
        'source_diff_sha256': sha(work/'source.diff'), 'original_root_inputs_sha256': root_hashes,
        'app_files_sha256': app_hashes, 'zip': zip_path.name, 'zip_sha256': sha(zip_path),
        'architecture': architecture, 'codesign_output': signature.stderr,
        'signing': 'No developer identity, notarization or resource seal. Mach-O contains a linker ad-hoc signature only.',
        'checks': {'simulation_unit_passed': 195, 'simulation_vectors_passed': 7, 'simulation_ignored': 2,
                   'desktop_passed': 106, 'desktop_ignored': 5, 'python_helpers_passed': args.helper_count,
                   'frontend_passed': 457, 'frontend_skipped': 1, 'browser_passed': args.browser_count,
                   'independent_harmonic_cases_passed': 19, 'real_project_cases_passed': 3,
                   'native_process_startup': startup['status']},
        'reference_maximum_region_relative_difference': max(c['maximum_region_relative_difference'] for c in reference['cases'].values()),
        'receipts_sha256': {name+'.command.json': sha(archive/(name+'.command.json')) for name in receipts},
        'limitations': ['Linear periodic planar moving-PM source only; no finite housing edges/slots/entry-exit/acceleration',
            'Magnetic shielding retains explicitly limited effective-DC fundamental method, with no higher-harmonic tail qualification',
            'Driver diagnostics remain fundamental-only; do not compare as identical models',
            'No winding-current reaction, induced PCB-copper shielding, nonlinear winding coupling or differential inductance qualification',
            'No temperature/hotspot/hardware claim;100C desired ceiling is absolute and requires separate thermal assumptions',
            'Native startup process observed only; no automated WKWebView interaction/end-to-end test'],
        'browser_report': str(browser_path),
        'preserved_failures': ['Browserv1: four newly migrated tests had wrong view-switch/default-panel selectors; corrected without relocating UI controls',
            'Browserv2:99/100 passed; modal autofocus race sent peak-current typing into name. Test waits for initial focus; finalv3 passes100/100',
            'Broader workspace-browser-full-v1/v2 aborted at8failures and remain archived; partial/skipped runs do not qualify acceptance',
            'Keyboard submenu focus and dock scroll diagnostic failures remain archived with traces; final selected browser report establishes current coverage',
            'Earlier authored Rust tests used wrong region index, arbitrary minimum harmonic count and out-of-bounds doubledBr. Test assumptions corrected; no production gates relaxed',
            'All preexisting reference failures and original overlap rejection remain preserved in archive'],
    }
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'): report['command_receipt'] = os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    (work/'verification.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    (work/'SHA256SUMS').write_text(''.join(f'{sha(work/name)}  {name}\n' for name in
        [zip_path.name, 'source.tar.gz', 'source.diff', 'verification.json']))
    print(report['status'], zip_path, report['zip_sha256'], flush=True)


if __name__ == '__main__': main()
