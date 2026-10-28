#!/usr/bin/env python3
"""Export and check copper geometry from a saved material-bearing version.

Only an archived derived copy has backplane=null so the existing free-space
exporter can validate resistance, currents and conductor quadrature. The source
project is never edited. These free-space forces do not validate the original
material response. The original material model and source hash remain explicit.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

from check_free_space import run
from post_project_force import sha
from source_snapshot import capture


def geometry_copy(project,version):
    result=copy.deepcopy(project)
    config=result['versions'][version]['state']['config']
    material=copy.deepcopy(config.get('backplane'))
    config['backplane']=None
    return result,material


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--version',type=int,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--meshes',type=int,nargs='+',default=[20,40,80])
    args=parser.parse_args();project=args.project.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous winding exports')
    original=json.loads(project.read_text());source_sha=sha(project)
    if not 0<=args.version<len(original['versions']):parser.error('Invalid saved version')
    derived,material=geometry_copy(original,args.version)
    work.mkdir(parents=True);source=work/'original.pmmotor';source.write_bytes(project.read_bytes())
    path=work/'geometry-only.pmmotor';path.write_text(json.dumps(derived,indent=2)+'\n')
    snapshots=capture(work,[Path(__file__),Path(__file__).with_name('check_winding_oracle.py'),Path(__file__).with_name('winding_coordinates.py')])
    report={'status':'running','scope':__doc__,'source_project_sha256':source_sha,'version_index':args.version,
        'derived_project_sha256':sha(path),'original_backplane':material,
        'saved_mover_position_mm':original['versions'][args.version]['state']['mover_position_mm'],
        'only_derived_change':'versions[selected].state.config.backplane=null',
        'source_snapshots':snapshots,'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        elapsed=run([sys.executable,str(Path(__file__).with_name('check_winding_oracle.py').resolve()),
            '--project',str(path),'--version',str(args.version),'--meshes',*[str(v) for v in args.meshes],
            '--work',str(work/'free-space-copper-audit')],work,'export.log')
        copper=json.loads((work/'free-space-copper-audit/summary.json').read_text())
        if copper['status']!='passed-independent-winding-and-free-space-force-only' or copper['failures']:
            raise ValueError('Copper geometry/current/quadrature check failed')
        # Restore the single documented change and require exact source equality.
        restored=json.loads(path.read_text());restored['versions'][args.version]['state']['config']['backplane']=material
        if restored!=original or sha(project)!=source_sha or sha(source)!=source_sha:
            raise ValueError('Source geometry or original project changed')
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Export implementation changed')
        report.update(status='passed-original-version-copper-export-only',seconds=elapsed,
            copper_audit_sha256=sha(work/'free-space-copper-audit/summary.json'))
        save();print(report['status'],flush=True)
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise


if __name__=='__main__':main()
