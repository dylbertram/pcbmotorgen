import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from force_checkpoint import compatible_checkpoint
from post_project_force import sha


class ForceCheckpointTest(unittest.TestCase):
    def test_only_matching_interrupted_quadrature_units_are_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);physics=root/'physics.py';physics.write_text('immutable physics')
            path=root/'partial.json';receipt=root/'partial.command.json';receipt.write_text(json.dumps({'status':'interrupted'}))
            metadata={'source_hashes':{'mesh':'m','solution':'s','summary':'r'},'backend':'NGSolve','basis_order':2,
                'quadrature_depths_by_body':{'mover':[2,3],'stator':[0,1]},'force_path_family':'near-interface'}
            result={'force_n':[0,0,0],'triangle_depth':0,'faces':{f'{axis}/{side}':{
                'force_n':[0,0,0],'area_m2':4.,'expected_area_m2':4.} for axis in range(3) for side in [-1,1]}}
            cached=dict(metadata,status='running',source_snapshots={'/old/physics.py':{'sha256':sha(physics)}},
                levels={'2':{'bare':{'stator':{'p':result}}}})
            path.write_text(json.dumps(cached))
            boxes={body:{'p':(np.array([-1.,-1.,-1.]),np.array([1.,1.,1.]))} for body in ['stator','mover']}
            self.assertEqual(compatible_checkpoint(path,receipt,metadata,{'physics.py':physics},boxes),cached['levels'])
            changed=copy.deepcopy(metadata);changed['source_hashes']['solution']='different'
            with self.assertRaises(ValueError):compatible_checkpoint(path,receipt,changed,{'physics.py':physics},boxes)
            bad=copy.deepcopy(cached);bad['levels']['2']['bare']['stator']['p']['force_n']=[1,0,0]
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):compatible_checkpoint(path,receipt,metadata,{'physics.py':physics},boxes)
            path.write_text(json.dumps(cached));physics.write_text('changed physics')
            with self.assertRaises(ValueError):compatible_checkpoint(path,receipt,metadata,{'physics.py':physics},boxes)
