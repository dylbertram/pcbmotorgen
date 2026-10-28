"""Reuse completed quadrature units from an interrupted POSTPROCESSING job.

The interrupted job is never relabelled as successful. A new supervisor must
finish a new report and rerun all gates. Bias-field hashes, numerical physics
code, surface geometry and quadrature settings must match before cached units
can be reused; missing units are recomputed from the completed field solution.
"""
import copy
import json
from pathlib import Path

import numpy as np

from post_project_force import sha


def compatible_checkpoint(path,receipt_path,metadata,physics_paths,boxes):
    cached=json.loads(path.read_text());receipt=json.loads(receipt_path.read_text())
    if cached.get('status')!='running' or receipt.get('status') not in ['interrupted','timeout']:
        raise ValueError('Only interrupted postprocessing checkpoints may be reused')
    for key in ['source_hashes','backend','basis_order','quadrature_depths_by_body','force_path_family']:
        if cached.get(key)!=metadata.get(key):raise ValueError('Checkpoint inputs or numerical settings differ: '+key)
    recorded={Path(name).name:entry['sha256'] for name,entry in cached['source_snapshots'].items()}
    for name,current in physics_paths.items():
        if recorded.get(name)!=sha(current):raise ValueError('Numerical field/integration implementation changed: '+name)
    levels=copy.deepcopy(cached.get('levels',{}))
    depth_labels=metadata['quadrature_depths_by_body']['mover']
    expected_faces={f'{axis}/{side}' for axis in range(3) for side in [-1,1]}
    for label,level in levels.items():
        if label not in [str(n) for n in depth_labels]:raise ValueError('Unexpected checkpoint quadrature level')
        index=depth_labels.index(int(label))
        for case,data in level.items():
            if case not in ['bare','stack']:raise ValueError('Unexpected cached field case')
            for body,surfaces in data.items():
                if body not in boxes:raise ValueError('Unexpected cached force body')
                for key,result in surfaces.items():
                    if key not in boxes[body]:raise ValueError('Unexpected cached force surface')
                    if type(result.get('triangle_depth')) is not int or result['triangle_depth']!=metadata['quadrature_depths_by_body'][body][index]:
                        raise ValueError('Wrong cached triangle depth')
                    if set(result.get('faces',{}))!=expected_faces:raise ValueError('Incomplete cached closed surface')
                    low,high=boxes[body][key];total=[]
                    for face,record in result['faces'].items():
                        axis=int(face.split('/')[0]);expected=float(np.prod(np.delete(high-low,axis)))
                        force=np.asarray(record['force_n'],dtype=float)
                        if force.shape!=(3,) or not np.isfinite(force).all():raise ValueError('Invalid cached traction')
                        if not np.isfinite([record['area_m2'],record['expected_area_m2'],expected]).all() or expected<=0 or abs(record['area_m2']/expected-1)>1e-8 or abs(record['expected_area_m2']/expected-1)>1e-8:
                            raise ValueError('Cached surface coverage/placement changed')
                        total.append(force)
                    force=np.asarray(result['force_n'],dtype=float)
                    if force.shape!=(3,) or not np.isfinite(force).all() or not np.allclose(force,np.sum(total,axis=0),rtol=1e-12,atol=1e-12):
                        raise ValueError('Cached resultant does not match its face tractions')
    return levels
