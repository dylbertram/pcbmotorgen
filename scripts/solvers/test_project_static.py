import copy
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from project_static import project, geometry, sif, getdp_input, check_force_paths, getdp_nonlinear_convergence, finish_report, main
from maxwell_stress import box_faces, force


CONFIG={'topology':'linear','magnet_count':5,'electrical_pitch_mm':12,'magnet_width_mm':5,
        'magnet_cross_width_mm':5,'magnet_height_mm':3,'magnet_remanence_t':1.34,
        'pcb_thickness_mm':1.6,'air_gap_mm':0.5,
        'backplane':{'layers':[{'material':'flex_ferrite','thickness_m':0.0002}],
                     'housing':{'material':'aluminum6061','thickness_m':0.001,'gap_m':0.0001}}}


class ProjectStaticTest(unittest.TestCase):
    def test_restored_stretched_mesh_keeps_the_explicit_elmer_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)/'job';source=Path(directory)/'source.pmmotor'
            source.write_text(json.dumps({'format':'pcbmotorgen-coil','format_version':1,'document_type':'motor',
                'versions':[{'state':{'config':CONFIG}}]}))
            argv=['project_static.py','--project',str(source),'--version','0','--footprint-mm','36','12',
                  '--array-centre-mm','0','0','--work',str(work),'--z-stretch','4','--gmsh','gmsh',
                  '--elmer','ElmerSolver','--elmergrid','ElmerGrid']
            with patch('sys.argv',argv),patch('project_static.run',side_effect=RuntimeError('stop before native meshing')):
                with self.assertRaisesRegex(RuntimeError,'stop before native meshing'):main()
            report=json.loads((work/'summary.json').read_text())
            self.assertEqual(report['backend'],'elmer');self.assertEqual(report['element_order'],1)
            self.assertEqual(report['mesh_coordinate_transform']['physical_node_z_divisor'],4)
            self.assertFalse(report['quarter_symmetry'])

    def test_changed_project_or_implementation_never_publishes_completed_status(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);source=work/'source.pmmotor';implementation=work/'analysis.py'
            source.write_text('original project');implementation.write_text('original analysis')
            (work/'project.msh').write_text('mesh')
            digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
            template={'model':{'source_sha256':digest(source)},'source_snapshots':{str(implementation):{'sha256':digest(implementation)}}}
            for status in ['comparison-only','completed-bare-field-only-unqualified']:
                report=copy.deepcopy(template)
                finish_report(report,source,work,status,[])
                self.assertEqual(json.loads((work/'summary.json').read_text())['status'],status)
                for path in [source,implementation]:
                    before=path.read_bytes();path.write_text('changed')
                    with self.assertRaises(ValueError):finish_report(copy.deepcopy(template),source,work,status,[])
                    failed=json.loads((work/'summary.json').read_text())
                    self.assertEqual(failed['status'],'failed');self.assertTrue(failed['failures'])
                    path.write_bytes(before)
                with self.assertRaises(ValueError):finish_report(copy.deepcopy(template),source,work,status,['force failed'])
                self.assertEqual(json.loads((work/'summary.json').read_text())['status'],'failed')

    def test_scalar_nonlinear_iteration_count_comes_from_the_real_log(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory)
            (job/'nonlinear.txt').write_text('1e-11 0\n')
            (job/'solve.log').write_text('Info    :   10 Nonlinear Residual norm 1e-11\n')
            self.assertEqual(getdp_nonlinear_convergence(job)['iterations'],10)
            (job/'solve.log').write_text('Info    :   10 Nonlinear Residual norm 1e-6\n')
            with self.assertRaises(ValueError):getdp_nonlinear_convergence(job)

    def test_rectangular_force_box_matches_the_chosen_footprint(self):
        faces=box_faces(0.018,-0.0016,0.0003,8,halfdepth=0.006)
        np.testing.assert_allclose(sum(normal*weight*len(points) for points,normal,weight in faces),0,atol=1e-18)
        self.assertAlmostEqual(faces[4][2]*64,0.036*0.012)
        fields=[np.tile([0.1,0.2,0.3],(len(points),1)) for points,_,_ in faces]
        np.testing.assert_allclose(force(faces,fields),0,atol=1e-14)
        self.assertLess(max(abs(points[:,1]).max() for points,_,_ in faces),0.0060001)

    def test_scalar_backend_preserves_region_materials_and_sample_pose(self):
        model=self.model()
        text=getdp_input(model)
        self.assertIn('Outer=Region[1001]',text)
        self.assertIn('Magnet=Region[{2,3,4,5,6}]',text)
        self.assertIn('br[Region[3]]=Vector[0,0,-1.3400000000000001]',text)
        self.assertIn('permeability[Region[7]]',text)
        self.assertIn('permeability[Region[8]]=(Mode==0) ? mu0 : mu0*1;',text)
        self.assertNotIn('br[Domain]',text) # GetDP forbids overlapping piecewise definitions
        self.assertIn('{60},Format SimpleTable',text)
        self.assertIn('OnElementsOf Air',text)
        self.assertIn('IterativeLoop[100,1e-9,Relaxation]',text)
        first_order=getdp_input(model,1)
        self.assertNotIn('BF_Node_2E',first_order)
        self.assertNotIn('NameOfCoef pe',first_order)
        self.assertIn('BF_Node;',first_order)
        with self.assertRaises(ValueError):getdp_input(model,3)

    def test_force_path_and_empty_stack_controls_are_not_ignored(self):
        def run(vectors):return {'stack_force_by_clearance_n':dict(zip(['a','b','c'],vectors))}
        runs={'bare':run([[0,0,0]]*3),'stack':run([[0,0,1]]*3)}
        self.assertEqual(check_force_paths(runs),[])
        runs['stack']['stack_force_by_clearance_n']['a']=[0,0,1.1]
        self.assertTrue(any('sensitivity' in item for item in check_force_paths(runs)))
        runs['bare']['stack_force_by_clearance_n']['b']=[0.1,0,0]
        self.assertTrue(any('floor' in item for item in check_force_paths(runs)))

    def model(self, config=None, version=0):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.pmmotor'
            path.write_text(json.dumps({'format':'pcbmotorgen-coil','format_version':1,'document_type':'motor',
                             'versions':[{'state':{'config':config or CONFIG,'mover_position_mm':41.4}}]}))
            before=path.read_bytes()
            model=project(path,version,[36,12],[0,0])
            self.assertEqual(path.read_bytes(),before)
            return model

    def test_explicit_pose_alternation_and_si_depths(self):
        model=self.model()
        self.assertEqual([m['polarization_t'][2] for m in model['magnets']],[1.34,-1.34,1.34,-1.34,1.34])
        centres=[m['origin_m'][0]+m['size_m'][0]/2 for m in model['magnets']]
        np.testing.assert_allclose(centres,[-0.012,-0.006,0,0.006,0.012],atol=1e-15)
        self.assertAlmostEqual(model['magnets'][0]['origin_m'][2],0.0021)
        self.assertAlmostEqual(model['stack'][0]['origin_m'][2],-0.0002)
        self.assertAlmostEqual(model['stack'][1]['origin_m'][2],-0.0013)
        self.assertEqual(model['saved_mover_position_mm_not_used'],41.4)

    def test_rejects_unknown_physics_instead_of_substituting_defaults(self):
        for key,value in [('topology','rotary'),('magnet_count',2.5),('magnet_remanence_t',float('nan')),
                          ('pcb_thickness_mm',0),('magnet_width_mm',7)]:
            config=copy.deepcopy(CONFIG);config[key]=value
            with self.assertRaises(ValueError):self.model(config)
        with self.assertRaises(ValueError):self.model(version=-1)

    def test_datasheet_overrides_and_static_only_housing(self):
        config=copy.deepcopy(CONFIG);config['backplane']['layers'][0].update(mu_r=145,bsat_t=0.3)
        model=self.model(config)
        self.assertEqual(model['stack'][0]['mu_r'],145)
        self.assertEqual(model['stack'][0]['bsat_t'],0.3)
        self.assertIn('INCLUDE HB_7',sif(model,True))
        self.assertNotIn('H-B Curve',sif(model,False))
        self.assertNotIn('Electric Conductivity = 25000000',sif(model,True))
        self.assertIn('Target Bodies(1) = $ magnet_4',sif(model,True))

    def test_air_boundary_tags_and_containment(self):
        model=self.model()
        text=geometry(model,0.0008,0.0001,0.06)
        self.assertIn('Physical Surface("outer",1001)',text)
        self.assertIn('Physical Volume("layer_0",7)',text)
        self.assertIn('Physical Volume("housing",8)',text)
        with self.assertRaises(ValueError):geometry(model,0.0008,0.0001,0.01)


if __name__=='__main__':
    unittest.main()
