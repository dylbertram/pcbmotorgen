#!/usr/bin/env python3
"""Fail-closed evidence audit for the experimental coreless app delivery.

Checks completed test/build receipts, current source copies, independent model
and real-project evidence, browser results, root-input preservation and the
native bundle. Does not upgrade planar tests to finite3D or hardware accuracy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def completed(receipt):
    if receipt.get('status')!='completed' or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0:
        raise ValueError('Whole job is not completed with successful integer exit code')


def verified_report(path,prefix):
    report=read(path)
    if not report.get('status','').startswith(prefix) or report.get('failures'):
        raise ValueError('Numerical report incomplete, failed or wrong scope: '+str(path))
    if not report.get('command_receipt'):raise ValueError('Missing supervisor receipt: '+str(path))
    completed(read(report['command_receipt']))
    for source,entry in report.get('source_snapshots',{}).items():
        if sha(source)!=entry['sha256'] or sha(Path(path).parent/entry['snapshot'])!=entry['sha256']:
            raise ValueError('Verified numerical source differs from current/archived implementation: '+source)
    return report


def browser_success(report):
    stats=report['stats']
    if stats['expected']<=0 or any(stats.get(k,0) for k in ['unexpected','skipped','flaky']):
        raise ValueError('Current-surface browser checks did not all pass without retries/skips')
    def visit(suites):
        for suite in suites:
            for spec in suite.get('specs',[]):
                for test in spec['tests']:
                    if test.get('expectedStatus')!='passed' or not test.get('results') or any(v['status']!='passed' for v in test['results']):
                        raise ValueError('Browser result is not an ordinary passed test')
            visit(suite.get('suites',[]))
    visit(report['suites'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['checks','browser','browser-receipt','reference','bundle','original-input-manifest','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--project-report',type=Path,action='append',required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier completion audits')
    checks=args.checks.resolve();batch=read(checks/'summary.json')
    if batch['status']!='completed-test-and-build-batch':raise ValueError('Test/build batch is not complete')
    required=['simulation','desktop','helpers','frontend','app-build']
    for label in required:
        if batch['checks'].get(label,{}).get('status')!='completed':raise ValueError('Missing passed check: '+label)
        completed(read(checks/(label+'.log.command.json')))
    for path,entry in batch['source_snapshots'].items():
        if sha(path)!=entry['sha256'] or sha(checks/entry['snapshot'])!=entry['sha256']:
            raise ValueError('Product source changed since test/build snapshot: '+path)
    browser=read(args.browser);browser_success(browser);completed(read(args.browser_receipt))
    reference_path=args.reference.resolve()/'summary.json';reference=verified_report(reference_path,'passed-independent-planar-housing-motion-only')
    if len(reference['cases'])<12 or any(not c['passed'] for c in reference['cases'].values()):raise ValueError('Independent reference cases missing')
    project_results=[]
    for path in args.project_report:
        value=verified_report(path,'passed-real-project-routing-housing-integration-only')
        if not value.get('routing_checks') or not all(c['passed'] for c in value['routing_checks'].values()):raise ValueError('Actual project winding checks missing')
        if value.get('explicit_pcb_depth_change_m') and not value.get('original_stack_rejection'):
            raise ValueError('Derived geometry correction lacks original rejection evidence')
        for source,digest in value['input_hashes'].items():
            if sha(source)!=digest:raise ValueError('Project/export/executable changed: '+source)
        binaries=[digest for source,digest in value['input_hashes'].items() if Path(source).name=='housing_motion_dump']
        if binaries!=[reference['binary_sha256']]:raise ValueError('Real project and independent reference used different Rust executables')
        project_results.append({'path':str(path),'sha256':sha(path),'segments':value['segments'],'vias':value['vias'],
            'explicit_pcb_depth_change_m':value.get('explicit_pcb_depth_change_m')})
    original=read(args.original_input_manifest);preserved={}
    for name,entry in original['files'].items():
        if Path(name).name==name and Path(name).suffix in ['.pmmotor','.dxf']:
            path=Path(original['root'])/name
            if sha(path)!=entry['sha256']:raise ValueError('Original root project/example changed: '+name)
            preserved[name]=entry['sha256']
    if not preserved:raise ValueError('No original root inputs were verified')
    bundle=args.bundle.resolve();info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes());name=info['CFBundleExecutable']
    if Path(name).name!=name:raise ValueError('Invalid bundle executable path')
    executable=bundle/'Contents/MacOS'/name;description=subprocess.check_output(['file',str(executable)],text=True).strip()
    if 'Mach-O' not in description or 'arm64' not in description:raise ValueError('Not a native Apple Silicon app executable')
    content=executable.read_bytes()
    for marker in [b'analyze_housing_motion',b'housing_joule_power_w',b'planar_travelling_fundamental_region_joule_v1']:
        if marker not in content:raise ValueError('Native app does not contain required housing capability marker')
    report={'status':'verified-experimental-coreless-app-delivery-scope-only','scope':__doc__,
        'test_build_batch':{'path':str(checks),'summary_sha256':sha(checks/'summary.json'),'checks':batch['checks']},
        'browser':{'path':str(args.browser),'sha256':sha(args.browser),'passed':browser['stats']['expected'],'projects':[p['name'] for p in browser['config']['projects']]},
        'reference':{'path':str(reference_path),'sha256':sha(reference_path),'cases':len(reference['cases']),
            'maximum_region_relative_difference':max(c['maximum_region_relative_difference'] for c in reference['cases'].values())},
        'real_project_checks':project_results,'preserved_root_inputs':preserved,
        'bundle':{'path':str(bundle),'version':info['CFBundleShortVersionString'],'executable_sha256':sha(executable),'file':description,
            'signing':'Local unsigned debug bundle; not notarized/distributed'},
        'limitations':['Declared periodic-planar steady-travel model, not arbitrary finite3D','No winding-field/copper-eddy reaction, full moving nonlinear shielding or thermal prediction',
            'No hardware ratings','Chromium UI and native command/unit tests; no automated native WKWebView end-to-end session',
            'Legacy expanded-modal UI tests target removed main-UI controls; failed attempts preserved and migration tracked as pcbmotorgen#0z3q, not claimed passed'],
        'source_tree':'User implementation remains uncommitted/unpushed; rebase backup/stash retained'}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(report['status'],flush=True)


if __name__=='__main__':main()
