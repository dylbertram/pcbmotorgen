from copy import deepcopy
import unittest

from dc_request_contract import UnsupportedDcRequest, physical_model, reference_snapshot, validate_request
from winding_oracle import resistances


class LiveDcRequestTest(unittest.TestCase):
    def inputs(self):
        fixture = dict(sim=dict(num_layers=2, pcb_thickness_m=.0008, min_trace_m=.0002,
            min_via_drill_m=.0003, min_via_annular_ring_m=.0001, backplane=None),
            drive=dict(outer_copper_oz=1., inner_copper_oz=1., via_plating_m=25e-6, winding_temp_c=75.),
            geometry_hints={'layer_z_m': []}, routing={'segments': [], 'vias': [], 'curves': []}, networks=[])
        network = dict(net='A', node_count=2, terminal=[0], star=[1],
            edges=[dict(a=0,b=1,geometry={'kind':'trace','layer':0,'points_m':[[0.,0.],[.01,0.]]})],
            rust_current_share=[1.])
        resistance = resistances(network, fixture['sim'], fixture['drive'], fixture['geometry_hints'])[0]
        network['edges'][0]['r_ohm'] = float(resistance)
        network['rust_resistance_ohm'] = float(resistance)
        fixture['networks'] = [network]
        model = dict(coordinate_convention='explicit', footprint_m=[.036,.012], pcb_thickness_m=.0008,
            magnets=[dict(origin_m=[0.,0.,.0013],size_m=[.005,.005,.003],polarization_t=[0,0,1.34])], stack=[])
        closure = dict(return_path_m=[[0.,0.,.001],[0.,.01,.001]], return_width_m=.0002,
                       return_thickness_m=35e-6, drive_path_m=[[0.,0.,.001],[0.,.001,.001]])
        request = dict(schema='finite-dc-live-request-v1', request_id='fresh-request', winding=reference_snapshot(fixture),
            material_model=physical_model(model), return_geometry=closure, source_basis_sha256='qualified-basis',
            current_a=.1, pm_offset_x_m=0., placement_acknowledged=True)
        return request, fixture, model, closure

    def test_eligibility_does_not_return_force_or_mutate_geometry(self):
        request, fixture, model, closure = self.inputs()
        before = deepcopy(request)
        result = validate_request(request, fixture, model, closure, 'qualified-basis')
        self.assertEqual(result['status'], 'eligible-for-recorded-geometry-live-recalculation-only')
        self.assertNotIn('force_n', result)
        self.assertEqual(request, before)

    def test_offline_circular_qualification_snapshot_is_not_an_app_capability(self):
        request, fixture, model, closure = self.inputs()
        request['winding']['schema'] = 'finite-dc-winding-circular-qualification-v1'
        with self.assertRaisesRegex(UnsupportedDcRequest, 'Actual live winding geometry snapshot required'):
            validate_request(request, fixture, model, closure, 'qualified-basis')

    def test_oversized_graph_is_rejected_before_allocating_a_current_solve(self):
        request, fixture, model, closure = self.inputs()
        request['winding']['networks'][0]['node_count'] = 1000000000
        with self.assertRaisesRegex(UnsupportedDcRequest, 'resource cap'):
            validate_request(request, fixture, model, closure, 'qualified-basis')

    def test_unsupported_current_pose_return_material_or_unknown_fields_rejected(self):
        for key, value in [('current_a', True), ('current_a', .2), ('pm_offset_x_m', 1e-5),
                           ('placement_acknowledged', False), ('source_basis_sha256', 'other'),
                           ('return_geometry', {}), ('material_model', {}), ('arbitrary_option', 'ignored')]:
            request, fixture, model, closure = self.inputs()
            request[key] = value
            with self.subTest(key=key,value=value), self.assertRaises(UnsupportedDcRequest):
                validate_request(request, fixture, model, closure, 'qualified-basis')

    def test_copper_width_depth_plating_temperature_and_network_changes_rejected(self):
        for mutation in ['width', 'depth', 'plating', 'temperature', 'node', 'nonfinite', 'bool', 'curve']:
            request, fixture, model, closure = self.inputs()
            winding = request['winding']
            if mutation == 'width':winding['sim']['min_trace_m'] *= 1.01
            if mutation == 'depth':winding['geometry_hints']['layer_z_m'] = [0., -.00081]
            if mutation == 'plating':winding['drive']['via_plating_m'] *= 1.01
            if mutation == 'temperature':winding['drive']['winding_temp_c'] = 20.
            if mutation == 'node':winding['networks'][0]['edges'][0]['a'] = 1
            if mutation == 'nonfinite':winding['sim']['min_trace_m'] = float('nan')
            if mutation == 'bool':winding['networks'][0]['edges'][0]['a'] = False
            if mutation == 'curve':winding['routing']['curves'] = [{'actual':'curve'}]
            with self.subTest(mutation=mutation), self.assertRaises((UnsupportedDcRequest, ValueError)):
                validate_request(request, fixture, model, closure, 'qualified-basis')

    def test_ui_stack_must_match_explicit_approved_materials_and_never_moves_them(self):
        request, fixture, model, closure = self.inputs()
        model['stack'] = [dict(name='layer_0', material='flex_ferrite', origin_m=[-.018,-.006,-.0002525],
            size_m=[.036,.012,.0002], mu_r=130., bsat_t=.25),
            dict(name='housing', material='aluminum6061', origin_m=[-.018,-.006,-.0013525],
                 size_m=[.036,.012,.001], mu_r=1., bsat_t=None)]
        request['material_model'] = physical_model(model)
        request['winding']['sim']['backplane'] = dict(layers=[dict(material='flex_ferrite',thickness_m=.0002)],
            housing=dict(material='aluminum6061',thickness_m=.001,gap_m=.0001))
        before = deepcopy(request)
        validate_request(request, fixture, model, closure, 'qualified-basis')
        self.assertEqual(before, request)
        for key, value in [('mu_r', False), ('mu_r', 0.), ('thickness_m', .00021), ('material', 'mn_zn_ferrite')]:
            changed = deepcopy(request)
            changed['winding']['sim']['backplane']['layers'][0][key] = value
            with self.subTest(key=key,value=value), self.assertRaises(UnsupportedDcRequest):
                validate_request(changed, fixture, model, closure, 'qualified-basis')
        changed = deepcopy(request)
        changed['material_model']['stack'][0]['origin_m'][2] += 1e-9
        with self.assertRaises(UnsupportedDcRequest):
            validate_request(changed, fixture, model, closure, 'qualified-basis')
