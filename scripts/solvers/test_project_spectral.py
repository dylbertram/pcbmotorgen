import copy
import json
import tempfile
import unittest
from pathlib import Path

from check_project_spectral import inputs
from test_project_static import CONFIG


class ProjectSpectralInputTest(unittest.TestCase):
    def read(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.pmmotor'
            path.write_text(json.dumps({'format':'pcbmotorgen-coil','format_version':1,'document_type':'motor',
                                       'versions':[{'state':{'config':config}}]}))
            before=path.read_bytes();result=inputs(path,0)
            self.assertEqual(path.read_bytes(),before)
            return result

    def test_actual_geometry_and_overrides_are_not_replaced_by_benchmark_defaults(self):
        config=copy.deepcopy(CONFIG);config['pcb_thickness_mm']=1.6
        config['backplane']['layers'][0].update(mu_r=145,bsat_t=0.3)
        _,stack,geometry,mu,bsat,digest=self.read(config)
        self.assertEqual(geometry['pcb'],0.0016)
        self.assertEqual(geometry['pole_pitch'],0.006)
        self.assertEqual((mu,bsat),(145,0.3))
        self.assertEqual(len(digest),64)

    def test_magnetic_housing_or_multiple_layers_require_a_different_model(self):
        config=copy.deepcopy(CONFIG);config['backplane']['housing']['material']='steel1018'
        with self.assertRaises(ValueError):self.read(config)
        config=copy.deepcopy(CONFIG);config['backplane']['layers']*=2
        with self.assertRaises(ValueError):self.read(config)


if __name__=='__main__':
    unittest.main()
