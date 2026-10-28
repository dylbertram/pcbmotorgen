#!/usr/bin/env python3
"""Create declared new saved app designs without editing the source project.

This does not generate substitute copper, move materials or qualify forces.
Each output must subsequently pass the actual host geometry export and controls.
"""
import argparse
import copy
import json
import math
from pathlib import Path

from post_project_force import sha
from source_snapshot import capture


def derive(document,version,case):
    if type(version) is not int or not 0<=version<len(document['versions']):raise ValueError('Explicit existing saved version required')
    result=copy.deepcopy(document);state=result['versions'][version]['state'];config=state['config']
    if state.get('cad_geometry') is not None or config.get('topology')!='linear':raise ValueError('Actual generated linear template required')
    if not case.get('id') or Path(case['id']).name!=case['id'] or case['id'] in ['.','..']:raise ValueError('Safe unique case identifier required')
    for key,value in case['config_overrides'].items():
        if key not in config or key in ['topology','drive','backplane']:raise ValueError('Unknown or physical-material override outside declared generation scope')
        config[key]=copy.deepcopy(value)
    for key,value in case['drive_overrides'].items():
        if key not in config['drive']:raise ValueError('Unknown saved drive setting')
        config['drive'][key]=copy.deepcopy(value)
    for key,value in case.get('state_overrides',{}).items():
        if key!='mover_position_mm' or key not in state:raise ValueError('Only an existing explicit saved linear mover pose may be declared')
        state[key]=copy.deepcopy(value)
    if 'mover_position_mm' in state:
        pose=state['mover_position_mm'];travel=config['desired_travel_mm']
        if isinstance(pose,bool) or not math.isfinite(pose) or not 0<=pose<=travel:
            raise ValueError('Saved mover pose exceeds declared new linear travel; no automatic clamp')
    if config['topology']!='linear':raise ValueError('No rotary substitution')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--declaration',type=Path,required=True)
    parser.add_argument('--template',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    if args.work.exists():parser.error('Preserve prior saved-design derivations')
    spec=json.loads(args.declaration.read_text());source=args.template.resolve()
    if spec['schema']!='linear-dc-generated-case-declarations-v1' or sha(source)!=spec['template_sha256']:
        raise ValueError('Declared original project identity changed')
    names=[case['id'] for case in spec['cases']]
    if not names or len(names)!=len(set(names)):raise ValueError('Unique declared actual design cases required')
    document=json.loads(source.read_text());version=spec['template_version_index']
    derived=[(case,derive(document,version,case)) for case in spec['cases']]
    args.work.mkdir(parents=True);outputs=[]
    for case,result in derived:
        path=args.work/(case['id']+'.pmmotor')
        with path.open('x') as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
        outputs.append(dict(case=case['id'],saved_project=str(path.resolve()),sha256=sha(path),version_index=version,
            config_overrides=case['config_overrides'],drive_overrides=case['drive_overrides'],
            state_overrides=case.get('state_overrides',{}),coverage=case['coverage']))
    if sha(source)!=spec['template_sha256']:raise ValueError('Original project changed during derivation')
    report=dict(status='prepared-declared-app-designs-no-geometry-or-physics-acceptance',scope=__doc__,
        input_hashes={str(source):sha(source),str(args.declaration.resolve()):sha(args.declaration)},cases=outputs,
        source_snapshots=capture(args.work,[Path(__file__)]))
    (args.work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(outputs),flush=True)


if __name__=='__main__':main()
