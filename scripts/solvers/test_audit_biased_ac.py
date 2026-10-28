import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from audit_biased_ac import audit,changes,load_verified,PHYSICS


def study():
    base={'case':'flex_0.2','frequency_hz':100000.,'material':{'mu':130},'knee_density':0,
          'resolution':{'layer_cells':32,'modes_per_phase':9,'angle_samples':512,'wall_cells':32,'gap_cells':4},
          'femm_sha256':{'unchanged':'input'},'source_strip_count':96,'femm_mesh_scale':1.,'femm_far_scale':1.,
          'spectral':{'coil_factors_per_phase':[[0.57,-0.07],[0.66,-0.06]]},'spectral_loss_w':[8e-5,7e-5],
          'femm_factors':[[0.57,-0.07],[0.66,-0.06]],'femm_loss_w':[8e-5,7e-5]}
    records={'base':base};previous=base
    for name,key,value in [('depth','layer_cells',64),('modes','modes_per_phase',17),('angles','angle_samples',1024),('wall','wall_cells',64),('gap','gap_cells',8)]:
        record=copy.deepcopy(previous);record['resolution'][key]=value;records[name]=record;previous=record
    for name,key,value in [('mesh','femm_mesh_scale',0.5),('far','femm_far_scale',2.),('source','source_strip_count',192)]:
        record=copy.deepcopy(previous);record[key]=value;records[name]=record
    return records


class AcAuditTest(unittest.TestCase):
    def test_changed_fields_failed_receipts_and_nan_residuals_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sources={};hashes={}
            for name in PHYSICS:
                snapshot=root/name;snapshot.write_text('pinned test source\n')
                sources[name]={'snapshot':name,'sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest()}
            names={'biased-ac.bias',*[f'biased-ac.{group}.p{phase}.{sheet}' for group in ['none','stack'] for phase in range(2) for sheet in range(2)]}
            for name in names:
                hashes[name]={}
                for key,suffix in [('input','.case.lua'),('output','.out')]:
                    path=root/(name+suffix);path.write_text('archived test artifact\n')
                    hashes[name][key]=hashlib.sha256(path.read_bytes()).hexdigest()
                (root/(name+'.receipt.json')).write_text(json.dumps({'status':'completed','exit_code':0,
                    'input_sha256':hashes[name]['input'],'output_sha256':hashes[name]['output']}))
            record={'status':'comparison-only','failures':[],'source_snapshots':sources,'femm_work':str(root),
                    'femm_sha256':hashes,'bias_convergence':{'relative_gradient_residual':1e-12},
                    'spectral':{'linear_residual':1e-12,'joule_coefficient_w_m2_t2':[1,2],'source_work_coefficient_w_m2_t2':[1,2]},
                    'femm_loss_w':[1,2],'femm_source_work_w':[1,2]}
            path=root/'summary.json'
            def save():path.write_text(json.dumps(record))
            save();load_verified(path)
            record['spectral']['linear_residual']=float('nan');save()
            with self.assertRaises(ValueError):load_verified(path)
            record['spectral']['linear_residual']=1e-12;save()
            artifact=root/'biased-ac.bias.out';artifact.write_text('changed\n')
            with self.assertRaises(ValueError):load_verified(path)
            artifact.write_text('archived test artifact\n')
            receipt=root/'biased-ac.bias.receipt.json';receipt.unlink()
            with self.assertRaises(FileNotFoundError):load_verified(path)
            receipt.write_text(json.dumps({'status':'timeout','exit_code':124}))
            with self.assertRaises(ValueError):load_verified(path)

    def test_separate_refinements_pass_and_missing_levels_do_not(self):
        records=study();self.assertEqual(audit(records)['status'],'passed-periodic-small-signal-only')
        del records['wall']
        with self.assertRaises(ValueError):audit(records)

    def test_co_refined_or_mismatched_cases_are_rejected(self):
        for change in ['resolution','physics','femm']:
            records=study()
            if change=='resolution':records['depth']['resolution']['wall_cells']=64
            elif change=='physics':records['depth']['frequency_hz']=200000.
            else:records['far']['femm_mesh_scale']=0.5
            with self.assertRaises(ValueError):audit(records)

    def test_loss_and_added_effect_have_independent_gates(self):
        records=study();records['mesh']['femm_loss_w'][0]*=1.03
        self.assertEqual(audit(records)['status'],'failed')
        records=study();records['angles']['spectral']['coil_factors_per_phase'][0][1]*=1.1
        self.assertEqual(audit(records)['status'],'failed')

    def test_near_unity_factor_cannot_hide_a_wrong_material_effect(self):
        import numpy as np
        a=(np.array([[1.,-0.01],[1.,-0.01]]),np.ones(2))
        b=(np.array([[1.004,-0.01],[1.004,-0.01]]),np.ones(2))
        self.assertFalse(changes(a,b,relative=0.05)['passed'])


if __name__=='__main__':unittest.main()
