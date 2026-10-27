from copy import deepcopy
import unittest

from closed_winding import build
from dc_preparation import acceptance_matrix,actual_inputs,PREPARATION_TIMEOUT,STAGES,REMAINING,validate_prepared_summary
from dc_request_contract import reference_snapshot
from finite_copper_circuit import drive_segment
from winding_oracle import resistances


class RequestPreparationTest(unittest.TestCase):
    def test_preparation_freezes_the_full_later_matrix_without_relaxing_acceptance(self):
        matrix=acceptance_matrix('/actual/request.json')
        self.assertEqual(matrix['study_inputs'],'/actual/request.json')
        self.assertEqual(matrix['currents_loop_a'],[0.,.1,-.1,.5,-.5]);self.assertEqual(matrix['linear_offsets_x_m'],[0.,.0001,-.0001])
        self.assertEqual(matrix['relative_refinement_gate'],.02);self.assertEqual(matrix['relative_independent_gate'],.05)
        self.assertEqual(matrix['source_controls']['port_fraction'],[.5,.4]);self.assertEqual(matrix['force_vector_floor_n'],1e-8)

    def request(self):
        fixture=dict(sim=dict(num_layers=2,pcb_thickness_m=.0008,min_trace_m=.0002,min_via_drill_m=.0003,
            min_via_annular_ring_m=.0001,backplane=None,active_area_length_m=.01,board_width_m=.01),
            drive=dict(outer_copper_oz=1.,inner_copper_oz=1.,via_plating_m=25e-6,winding_temp_c=75.),
            geometry_hints={'layer_z_m':[]},routing=dict(segments=[],vias=[],curves=[]),networks=[])
        for net,start in [('A',[.001,.002]),('B',[.001,.004])]:
            network=dict(net=net,node_count=2,terminal=[0],star=[1],rust_current_share=[1.],
                edges=[dict(a=0,b=1,geometry=dict(kind='trace',layer=0,points_m=[start,[.005,.005]]))])
            resistance=float(resistances(network,fixture['sim'],fixture['drive'],fixture['geometry_hints'])[0])
            network['edges'][0]['r_ohm']=resistance;network['rust_resistance_ohm']=resistance;fixture['networks'].append(network)
        snapshot=reference_snapshot(fixture);_,_,closure=build(snapshot,'A','B',[-.005,-.005,.0008],[[-.006,-.001,.0008],[-.006,-.003,.0008]])
        start,end=drive_segment(closure['return_path_m'],.0002,.5)
        model=dict(coordinate_convention='explicit',footprint_m=[.01,.01],pcb_thickness_m=.0008,
            magnets=[dict(tag=2,name='magnet_0',origin_m=[-.002,-.002,.0013],size_m=[.005,.005,.003],polarization_t=[0,0,1.34])],
            stack=[dict(tag=3,name='layer_0',material='flex_ferrite',origin_m=[-.005,-.005,-.0002],size_m=[.01,.01,.0002],mu_r=130.,bsat_t=.25)])
        return dict(schema='finite-dc-live-request-v2',request_id='actual-preparation',winding=snapshot,material_model=model,
            return_geometry=dict(return_path_m=closure['return_path_m'],return_width_m=.0002,return_thickness_m=35e-6,
                drive_path_m=[start.tolist(),end.tolist()]),current_a=.1,pm_offset_x_m=0.,placement_acknowledged=True)

    def test_actual_return_and_model_are_bound_without_mutating_or_returning_force(self):
        request=self.request();before=deepcopy(request);actual=actual_inputs(request)
        self.assertEqual(request,before);self.assertEqual(actual['snapshot'],request['winding'])
        self.assertEqual(actual['model'],request['material_model']);self.assertNotIn('force_n',actual)
        self.assertLess(sum(STAGES.values())+60,PREPARATION_TIMEOUT)

    def test_return_material_or_drive_cannot_be_silently_repaired(self):
        for change in ['endpoint','width','drive','model','ack','curve']:
            request=self.request()
            if change=='endpoint':request['return_geometry']['return_path_m'][0][0]+=.0001
            elif change=='width':request['return_geometry']['return_width_m']*=1.01
            elif change=='drive':request['return_geometry']['drive_path_m'][0][1]+=.00001
            elif change=='model':request['material_model']['footprint_m'][0]*=1.01
            elif change=='ack':request['placement_acknowledged']=False
            else:request['winding']['routing']['curves']=[{'actual':'curve'}]
            with self.subTest(change=change),self.assertRaises(ValueError):actual_inputs(request)

    def test_baseline_preparation_never_becomes_force_qualification(self):
        value=dict(status='prepared-request-bound-current-source-not-qualified',input_request_sha256='actual',
            source_status='prepared-baseline-needs-refinement',force_status='unqualified',remaining=REMAINING,
            artifacts={k:'immutable' for k in ['source','active','passive','return','independent','rt0']},evidence_hashes={'immutable':'hash'},
            stages={k:dict(state='completed',hard_timeout_s=v) for k,v in STAGES.items()})
        validate_prepared_summary(value,'actual')
        for change in ['force','sha','scope','missing']:
            changed=deepcopy(value)
            if change=='force':changed['pm_array_force_n']=[1,2,3]
            elif change=='sha':changed['input_request_sha256']='stale'
            elif change=='scope':changed['force_status']='qualified'
            else:del changed['artifacts']['passive']
            with self.subTest(change=change),self.assertRaises(ValueError):validate_prepared_summary(changed,'actual')
