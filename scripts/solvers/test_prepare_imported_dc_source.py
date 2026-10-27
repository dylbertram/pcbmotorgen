import unittest
from copy import deepcopy

from prepare_imported_dc_source import via_records, build, validate_geometry_reuse


class ImportedPhysicalCopperTest(unittest.TestCase):
    def snapshot(self):
        return dict(schema='finite-dc-winding-circular-qualification-v1',
            sim=dict(num_layers=4, pcb_thickness_m=.0008, min_trace_m=.0002, min_via_drill_m=.0003, min_via_annular_ring_m=.0001),
            drive=dict(outer_copper_oz=1.,inner_copper_oz=1.,via_plating_m=25e-6,winding_temp_c=75.),
            geometry_hints=dict(layer_z_m=[-.0048,-.0032,-.0016,0.]),
            routing=dict(segments=[],curves=[],vias=[dict(position=dict(x=1.,y=2.),from_layer=0,to_layer=3,net='A')]),
            networks=[dict(net='A',edges=[dict(geometry=dict(kind='via',position_m=[.001,.002],layers=[1,2]))])])

    def test_full_raw_through_barrel_and_pad_planes_not_truncated_to_inner_landings(self):
        snapshot = self.snapshot();before=deepcopy(snapshot)
        via=next(iter(via_records(snapshot).values()))
        self.assertEqual(via['layers'],{0,1,2,3})
        self.assertAlmostEqual(via['high']-via['low'],.0048+35e-6)
        shape,spec=build(snapshot)
        self.assertEqual(spec['full_physical_via_stubs'][0]['electrical_landing_range_m'],[-.0032,-.0016])
        # Independent cylinder/annulus volume includes all four finite pads,
        # subtracting the barrel/pad overlaps once per copper plane.
        import math
        barrel_area=math.pi*((.000175)**2-(.00015)**2)
        extra_pad=math.pi*((.00025)**2-(.000175)**2)
        expected=barrel_area*(.0048+35e-6)+4*extra_pad*35e-6
        self.assertAlmostEqual(shape.mass/expected,1.,places=9)
        self.assertEqual(snapshot,before)

    def test_separate_blind_vias_do_not_gain_a_filled_barrel_gap(self):
        snapshot=self.snapshot()
        snapshot['routing']['vias']=[dict(position=dict(x=1.,y=2.),from_layer=0,to_layer=1,net='A'),
                                    dict(position=dict(x=1.,y=2.),from_layer=2,to_layer=3,net='A')]
        via=next(iter(via_records(snapshot).values()))
        self.assertEqual(len(via['spans']),2)
        self.assertLess(via['spans'][0]['high'],via['spans'][1]['low'])
        shape,spec=build(snapshot)
        self.assertEqual(spec['physical_via_spans'],2)
        self.assertEqual(spec['gapped_via_positions'],1)
        self.assertEqual(len(shape.solids),2)
        from netgen.occ import Box,Pnt
        gap=shape*Box(Pnt(0.,0.,-.0031),Pnt(.01,.01,-.0017))
        self.assertEqual(gap.mass,0.)

    def test_geometry_checkpoint_cannot_import_changed_inputs_or_unknown_failures(self):
        from pathlib import Path
        from finite_copper_geometry import dimensions
        from post_project_force import sha
        snapshot=self.snapshot();inputs={'immutable':'hash'}
        paths=[Path(__file__).with_name(name) for name in ['finite_circular_copper.py','finite_copper_geometry.py',
            'closed_winding.py','winding_oracle.py','source_snapshot.py']]
        prior=dict(status='failed',error="'str' object has no attribute 'read_bytes'",input_hashes=inputs,
            geometry=dimensions(snapshot),source_snapshots={str(path):{'sha256':sha(path)} for path in paths})
        validate_geometry_reuse(prior,inputs,snapshot)
        for change in ['inputs','status','dimensions','source']:
            changed=deepcopy(prior)
            if change=='inputs':changed['input_hashes']={}
            if change=='status':changed['status']='running'
            if change=='dimensions':changed['geometry']['via_plating_m']*=2
            if change=='source':changed['source_snapshots']={}
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_geometry_reuse(changed,inputs,snapshot)
