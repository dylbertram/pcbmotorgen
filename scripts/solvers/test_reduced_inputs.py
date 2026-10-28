import copy
import json
import tempfile
import unittest
from pathlib import Path

from project_static import project
from reduced_inputs import validate_reduced_inputs
from reduced_potential import formulation, response_model
from source_snapshot import capture
from test_project_static import CONFIG


class ReducedInputsTest(unittest.TestCase):
    def test_metadata_source_law_and_material_bounds_must_match_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);source=work/'source.pmmotor'
            source.write_text(json.dumps({'format':'pcbmotorgen-coil','format_version':1,'document_type':'motor',
                'versions':[{'state':{'config':CONFIG}}]}))
            model=project(source,0,[36,12],[0,0]);solver=response_model(model,False,True)
            job=work/'bare';job.mkdir();(job/'project.pro').write_text(formulation(model,solver))
            low=solver['stack'][0]['origin_m'];size=solver['stack'][0]['size_m'];high=[a+b for a,b in zip(low,size)]
            vertices=[low,[high[0],low[1],low[2]],[low[0],high[1],low[2]],high]
            def mesh(offset):
                rows=[f'{i+1} {v[0]+offset:.17g} {v[1]:.17g} {v[2]:.17g}' for i,v in enumerate(vertices)]
                return '$Nodes\n4\n'+'\n'.join(rows)+'\n$EndNodes\n$Elements\n1\n1 4 2 7 7 1 2 3 4\n$EndElements\n'
            (work/'project.msh').write_text(mesh(0))
            report={'model':model,'solver_geometry_model':solver,'quarter_symmetry':False,'omit_inert_regions':True,
                    'source_snapshots':capture(work,[source]),'runs':{'bare':{}}}
            self.assertEqual(validate_reduced_inputs(work,report),solver)
            changed=copy.deepcopy(report);changed['model']['magnets'][0]['polarization_t'][2]=1.35
            with self.assertRaisesRegex(ValueError,'archived project'):validate_reduced_inputs(work,changed)
            (work/'project.msh').write_text(mesh(.001))
            with self.assertRaisesRegex(ValueError,'material bounds'):validate_reduced_inputs(work,report)
            (work/'project.msh').write_text(mesh(0));(job/'project.pro').write_text('changed constitutive law')
            with self.assertRaisesRegex(ValueError,'source/material expressions'):validate_reduced_inputs(work,report)
