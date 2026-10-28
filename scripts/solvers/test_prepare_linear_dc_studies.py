import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from prepare_linear_dc_studies import model_inputs,host_exports


class LinearPhysicalInputTest(unittest.TestCase):
    def test_actual_host_test_prefix_and_standalone_export_are_recognized(self):
        value=dict(source_project='actual',source_sha256='hash',version_index=1,snapshot='actual-snapshot',snapshot_sha256='snap',imported=False,qualification_only=False)
        text=json.dumps(value);prefix='test commands::dc_jobs::tests::export_saved_dc_geometry_for_independent_qualification ... '
        self.assertEqual(host_exports(text),[value]);self.assertEqual(host_exports(prefix+text+'\nok'),[value])
        self.assertEqual(host_exports('unknown-log-prefix '+text),[])

    def test_saved_pose_coordinate_transform_and_positive_stack_gap_not_a_correction(self):
        snapshot=dict(sim=dict(active_area_length_m=.029,board_width_m=.008,pcb_thickness_m=.0012,
            magnet_count=3,magnet_pitch_m=.006,min_trace_m=.0002),routing=dict(segments=[dict(layer=1)]))
        spec=dict(layers=[dict(layer=0,centre_z_m=0.,thickness_m=35e-6),dict(layer=1,centre_z_m=-.0004,thickness_m=35e-6)])
        model=dict(stack=[dict(origin_m=[-.0145,-.004,-.0002],size_m=[.029,.008,.0002])])
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'actual.pmmotor';source.write_text(json.dumps(dict(versions=[dict(state=dict(config=dict(topology='linear',desired_travel_mm=12.),cad_geometry=None,mover_position_mm=6.))])))
            with patch('prepare_linear_dc_studies.geometry_descriptor'),patch('prepare_linear_dc_studies.project',return_value=model) as made,patch('prepare_linear_dc_studies.translation',return_value=np.array([-.0145,-.004,.0012])),patch('prepare_linear_dc_studies.dimensions',return_value=spec),patch('prepare_linear_dc_studies.via_records',return_value={}),patch('prepare_linear_dc_studies.closed_graph',return_value=(None,None,{})):
                result=model_inputs(snapshot,source,0,[[-.02,.006,.0008]],'A','C')
                self.assertAlmostEqual(result['preflight']['vertical_separation_m'],.0007825)
                self.assertEqual(result['model'],model);self.assertAlmostEqual(made.call_args.args[3][0],-2.5)
                with patch('prepare_linear_dc_studies.translation',return_value=np.array([0.,0.,0.])):
                    with self.assertRaisesRegex(ValueError,'moved physical'):model_inputs(snapshot,source,0,[],'A','C')
