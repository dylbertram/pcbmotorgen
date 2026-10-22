"""Verify an ended resource-limited mesh checkpoint; never import its fields."""
import json
from pathlib import Path

import numpy as np

from job_status import process_identity
from post_project_force import sha


def validate_checkpoint(prior,expected,receipt):
    mesh_only=(prior.get('status')=='completed-linear-study-mesh-only' and receipt.get('status')=='completed'
        and type(receipt.get('exit_code')) is int and receipt['exit_code']==0)
    limited=receipt.get('status') in ['memory-limit','timeout'] and prior.get('status') in ['running','failed']
    if not (mesh_only or limited) or 'solution_sha256' in prior or 'dc' in prior:
        raise ValueError('Only ended mesh-only/resource-limited checkpoints without accepted fields may be reused')
    for key in ['version','input_hashes','geometry','brep_sha256']:
        if prior[key]!=expected[key]:raise ValueError('Mesh checkpoint changed actual source inputs or controls: '+key)
    if {k:v for k,v in prior['request'].items() if k!='mesh_only'}!={k:v for k,v in expected['request'].items() if k!='mesh_only'}:
        raise ValueError('Mesh checkpoint changed source controls')
    if any(prior.get('study_bindings',{}).get(key)!=value for key,value in expected['study_bindings'].items()):
        raise ValueError('Mesh checkpoint changed declared physical study')
    quality=prior['geometric_volume_check'];errors=prior['cad_partition_checks']
    values=[quality['relative_difference'],errors['physical_union_relative_error'],errors['drive_volume_relative_error']]
    if not np.isfinite(values).all() or min(values)<0 or values[0]>.02 or max(values[1:])>1e-9:
        raise ValueError('Saved mesh did not pass unchanged CAD/partition gates')
    if not 0<prior['estimated_dofs']<=expected['request']['max_dofs'] or prior['materials']!=['copper','drive']:
        raise ValueError('Saved mesh exceeds source cap or changed conductor tags')


def load_checkpoint(origin,expected):
    origin=Path(origin).resolve();path=origin/'summary.json';prior=json.loads(path.read_text())
    receipt_path=Path(prior['command_receipt']);receipt=json.loads(receipt_path.read_text())
    command=receipt['command']
    if '--work' not in command or Path(command[command.index('--work')+1]).resolve()!=origin:
        raise ValueError('Checkpoint receipt belongs to another job')
    validate_checkpoint(prior,expected,receipt)
    for pid_key,identity_key in [('pid','process_identity'),('supervisor_pid','supervisor_identity')]:
        if receipt.get(pid_key):
            actual=process_identity(receipt[pid_key]);saved=receipt.get(identity_key,{})
            if actual and actual.get('boot_id')==saved.get('boot_id') and actual.get('start_ticks')==saved.get('start_ticks'):
                raise ValueError('Mesh checkpoint worker/supervisor is still live')
    paths={str(p):sha(p) for p in [path,receipt_path,origin/'mesh.vol',origin/'closed-copper.brep']}
    if paths[str(origin/'mesh.vol')]!=prior['mesh_sha256'] or paths[str(origin/'closed-copper.brep')]!=prior['brep_sha256']:
        raise ValueError('Saved mesh/BRep checkpoint changed')
    for name,digest in (prior['input_hashes']|prior['study_bindings']).items():
        if sha(Path(name))!=digest:raise ValueError('Mesh checkpoint physical evidence changed')
    physics=['finite_copper_circuit.py','finite_copper_curvature.py','finite_copper_current.py','prepare_linear_dc_copper.py']
    for name,entry in prior['source_snapshots'].items():
        archived=origin/entry['snapshot']
        if sha(archived)!=entry['sha256']:raise ValueError('Checkpoint archived implementation changed')
        if Path(name).name in physics and sha(Path(name))!=entry['sha256']:raise ValueError('Checkpoint physics implementation changed')
    if not set(physics)<={Path(name).name for name in prior['source_snapshots']}:raise ValueError('Incomplete checkpoint physics provenance')
    return prior,paths
