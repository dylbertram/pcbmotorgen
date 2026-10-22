"""Request-bound finite current preparation. Never qualifies or returns force."""
from copy import deepcopy
import itertools

import numpy as np

from closed_winding import build as closed_graph
from dc_applicability import inspect_request
from dc_request_contract import encoded,geometry_descriptor
from finite_copper_circuit import drive_segment
from finite_copper_geometry import dimensions
from prepare_linear_dc_material_model import validate_model

PREPARATION_TIMEOUT=14400
STAGES={'geometry':1800,'source':5400,'active':3600,'passive':1800,'return':300,'independent':600,'rt0':600}
REMAINING=['isolated mesh/drive-length/curvature current controls','predetermined near-copper/material field controls',
           'complete independent nonlinear magnetic and source-refinement force controls','exact-case admission and fresh saved-host acceptance']


def acceptance_matrix(request_path):
    """Freeze all later acceptance requirements before the baseline is solved."""
    return dict(schema='declared-linear-dc-acceptance-matrix-v1',study_inputs=str(request_path),
        currents_loop_a=[0.,.1,-.1,.5,-.5],linear_offsets_x_m=[0.,.0001,-.0001],
        source_controls=dict(mesh_m=[.0002,.00015],curvature_safety=[4.,6.],port_fraction=[.5,.4],
            independent_electrical='H1 vs mixed HDiv with complete eligible local/passive/return checks'),
        magnetic_baseline=dict(material_mesh_m=.0012,air_mesh_m=.01,air_radius_m=.06,vector_order=1,quadrature_degree=8,source_opening=.075),
        isolated_magnetic_controls=dict(material_mesh_m=.0009,air_radius_m=.08,quadrature_degree=10,source_opening=.0375,higher_order_limit_control=2),
        relative_refinement_gate=.02,relative_independent_gate=.05,force_vector_floor_n=1e-8,field_floor_t=1e-12,
        section_current_floor_per_loop_a=1e-8,coverage='Full 37-job magnetic template, all three source axes through downstream forces, zero/linear/vacuum limits and complete sampled states. Baseline preparation alone never satisfies these requirements.')


def actual_inputs(request):
    result=inspect_request(request,[])
    if result['state']!='preparation-required':raise ValueError(result['reason'])
    snapshot=deepcopy(request['winding']);geometry_descriptor(snapshot);model=deepcopy(request['material_model']);validate_model(model)
    sim=snapshot['sim'];spec=dimensions(snapshot)
    shift=[-sim['active_area_length_m']/2,-sim['board_width_m']/2,sim['pcb_thickness_m']]
    if model['footprint_m']!=[sim['active_area_length_m'],sim['board_width_m']] or model['pcb_thickness_m']!=sim['pcb_thickness_m']:
        raise ValueError('Preparation requires explicit app footprint/PCB thickness without inferred rescaling')
    returned=request['return_geometry'];points=np.asarray(returned['return_path_m'],dtype=float)
    if points.shape!=(4,3) or not np.isfinite(points).all():raise ValueError('Explicit finite three-segment return required')
    layer=spec['layers'][0]
    if returned['return_width_m']!=layer['trace_width_m'] or returned['return_thickness_m']!=layer['thickness_m']:
        raise ValueError('Declared return cross-section must match actual outer copper; no fitted return')
    start,end=drive_segment(points,layer['trace_width_m'],.5)
    if encoded(returned['drive_path_m'])!=encoded([start.tolist(),end.tolist()]):
        raise ValueError('Explicit drive path must match the declared central half-length control')
    matches=[]
    networks=snapshot['networks']
    if len(networks)>8:raise ValueError('Source preparation supports at most eight declared phases')
    for positive,negative in itertools.permutations([n['net'] for n in networks],2):
        try:_,_,closure=closed_graph(snapshot,positive,negative,shift,points[1:3].tolist())
        except ValueError:continue
        if encoded(closure['return_path_m'])==encoded(points.tolist()):matches.append(closure)
    if len(matches)!=1:raise ValueError('Return endpoints must identify exactly two actual terminal phases without tolerance matching')
    return dict(snapshot=snapshot,model=model,translation_m=shift,closure=matches[0],
        return_width_m=layer['trace_width_m'],return_thickness_m=layer['thickness_m'])


def validate_prepared_summary(value,request_sha):
    if (value.get('status')!='prepared-request-bound-current-source-not-qualified' or value.get('input_request_sha256')!=request_sha
        or value.get('force_status')!='unqualified' or value.get('source_status')!='prepared-baseline-needs-refinement'
        or value.get('remaining')!=REMAINING or any(key in value for key in ['pm_array_force_n','qualified_case','force_n'])):
        raise ValueError('Unverified preparation report or an unqualified force was returned')
    required={'source','active','passive','return','independent','rt0'}
    if set(value.get('artifacts',{}))!=required:raise ValueError('Incomplete request-bound current-source preparation')
    if not value.get('evidence_hashes'):raise ValueError('Prepared current lacks immutable evidence bindings')
    stages=value.get('stages',{})
    if set(stages)!=set(STAGES) or any(v.get('state')!='completed' or v.get('hard_timeout_s')!=STAGES[k] for k,v in stages.items()):
        raise ValueError('Every bounded baseline-preparation stage must complete')
