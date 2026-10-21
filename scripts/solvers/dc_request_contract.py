"""Exact-geometry eligibility for future live DC jobs, never archived forces.

The first admitted scope is the recorded source geometry, explicit return and
approved disjoint material placement at the sampled current/pose points. Other
geometry must be qualified separately; equality has no dimensional tolerance.
This contract neither solves fields nor changes a caller's physical geometry.
"""
from copy import deepcopy
import hashlib
import json
import math

from finite_copper_geometry import dimensions
from finite_current_zero_bias import posed_model
from project_static import LAYERS, HOUSINGS
from winding_oracle import layer_z, resistances, unit_currents


class UnsupportedDcRequest(ValueError):
    pass


def canonical(value):
    """Ignore JSON numeric spelling, never physical differences or booleans."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (float, int)):
        if not math.isfinite(value):
            raise UnsupportedDcRequest('Nonfinite request data cannot enter a DC job')
        return float(value) if value else 0.
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: canonical(item) for key, item in value.items()}
    raise UnsupportedDcRequest('Unsupported JSON value in DC request')


def encoded(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def geometry_descriptor(snapshot):
    if snapshot.get('schema') != 'finite-dc-winding-geometry-v1':
        raise UnsupportedDcRequest('Actual live winding geometry snapshot required')
    spec = dimensions(snapshot)
    sim = deepcopy(snapshot['sim'])
    layers = [{'layer': item['layer'], 'centre_z_m': item['centre_z_m'], 'thickness_m': item['thickness_m'],
               'trace_width_m': item['trace_width_m']} for item in spec['layers']]
    finite = dict(layers=layers, via_drill_m=sim['min_via_drill_m'],
                  via_annular_ring_m=sim['min_via_annular_ring_m'], via_plating_m=spec['via_plating_m'],
                  resistivity_ohm_m=spec['copper_resistivity_ohm_m'], temperature_c=spec['temperature_c'])
    if encoded(snapshot['finite_copper']) != encoded(finite):
        raise UnsupportedDcRequest('Finite copper dimensions/resistivity disagree with actual settings')
    if any(snapshot['routing'].get(key) for key in ['curves', 'splines', 'io_traces', 'io_pads']):
        raise UnsupportedDcRequest('Curved/spline/IO copper is outside this finite-DC qualification')
    networks = sorted(snapshot['networks'], key=lambda item: item['net'])
    if not networks or len(networks) > 64 or len({network['net'] for network in networks}) != len(networks):
        raise UnsupportedDcRequest('Unique physical winding networks required')
    for network in networks:
        count = network['node_count']
        if type(count) is not int or count < 2 or not network['edges']:
            raise UnsupportedDcRequest('Explicit nonempty physical winding graph required')
        if count > 2048 or len(network['edges']) > 10000:
            raise UnsupportedDcRequest('Actual DC graph exceeds the declared preparation resource cap; no truncation applied')
        indices = [index for edge in network['edges'] for index in [edge['a'], edge['b']]]+network['terminal']+network['star']
        if any(type(index) is not int or not 0 <= index < count for index in indices):
            raise UnsupportedDcRequest('Winding graph node indices must be explicit valid integers')
        resistance = resistances(network, sim, snapshot['drive'], snapshot['geometry_hints'])
        shares, equivalent = unit_currents(network, resistance)
        if (any(abs(float(value)-edge['r_ohm']) > 1e-12*max(abs(float(value)), 1e-30)
                for value, edge in zip(resistance, network['edges'])) or
            len(shares) != len(network['rust_current_share']) or
            any(abs(float(a)-float(b)) > 1e-9 for a, b in zip(shares, network['rust_current_share'])) or
            abs(equivalent-network['rust_resistance_ohm']) > 1e-9*equivalent):
            raise UnsupportedDcRequest('Independent actual-network current/resistance check failed')
    # Stack placement is a separate REQUIRED physical input, not inferred from
    # nominal layer settings. Still retain its full caller value in the digest.
    depths = [layer_z(sim, snapshot['geometry_hints'], layer) for layer in range(sim['num_layers'])]
    return dict(sim=sim, routing=snapshot['routing'], networks=networks, finite_copper=finite,
                layer_depths_m=depths, terminals=snapshot['geometry_hints'].get('terminals', {}))


def reference_snapshot(fixture):
    snapshot = deepcopy(fixture)
    snapshot['schema'] = 'finite-dc-winding-geometry-v1'
    spec = dimensions(fixture)
    snapshot['finite_copper'] = dict(
        layers=[{key: layer[key] for key in ['layer', 'centre_z_m', 'thickness_m', 'trace_width_m']} for layer in spec['layers']],
        via_drill_m=fixture['sim']['min_via_drill_m'], via_annular_ring_m=fixture['sim']['min_via_annular_ring_m'],
        via_plating_m=spec['via_plating_m'], resistivity_ohm_m=spec['copper_resistivity_ohm_m'], temperature_c=spec['temperature_c'])
    return snapshot


def physical_model(model):
    return {key: model[key] for key in ['coordinate_convention', 'footprint_m', 'pcb_thickness_m', 'magnets', 'stack']}


def check_stack_settings(stack, model):
    # Nominal UI stack settings do not contain finite placement. The explicit
    # material_model supplies that placement, checked byte-for-byte separately.
    if stack is None:
        return
    if set(stack)-{'layers', 'housing'}:
        raise UnsupportedDcRequest('Unknown nominal stack settings')
    materials = [region for region in model['stack'] if region['name'] != 'housing']
    if len(stack.get('layers', [])) != len(materials):
        raise UnsupportedDcRequest('Nominal layer count differs from the explicit physical stack')
    for setting, region in zip(stack['layers'], materials):
        if set(setting)-{'material', 'thickness_m', 'mu_r', 'bsat_t'} or setting.get('material') not in LAYERS:
            raise UnsupportedDcRequest('Unsupported nominal magnetic layer')
        mu, bsat = LAYERS[setting['material']]
        law = [setting['material'], setting['thickness_m'], mu if setting.get('mu_r') is None else setting['mu_r'],
               bsat if setting.get('bsat_t') is None else setting['bsat_t']]
        if encoded(law) != encoded([region['material'], region['size_m'][2], region['mu_r'], region['bsat_t']]):
            raise UnsupportedDcRequest('Nominal layer law/thickness differs from the explicit physical stack')
    housing = stack.get('housing')
    regions = [region for region in model['stack'] if region['name'] == 'housing']
    if bool(housing) != bool(regions):
        raise UnsupportedDcRequest('Nominal housing differs from the explicit physical stack')
    if housing:
        region = regions[0]
        if set(housing)-{'material', 'thickness_m', 'gap_m'} or housing['material'] not in HOUSINGS:
            raise UnsupportedDcRequest('Unsupported nominal housing')
        if encoded([housing['material'], housing['thickness_m'], *HOUSINGS[housing['material']]]) != encoded(
            [region['material'], region['size_m'][2], region['mu_r'], region['bsat_t']]):
            raise UnsupportedDcRequest('Nominal housing law/thickness differs from physical geometry')
        above = min(item['origin_m'][2] for item in materials)
        gap = above-(region['origin_m'][2]+region['size_m'][2])
        # Only floating subtraction roundoff here; all origins/sizes and the
        # acknowledged placement are still compared exactly below.
        if not math.isclose(housing['gap_m'], gap, rel_tol=0., abs_tol=1e-15):
            raise UnsupportedDcRequest('Nominal housing gap differs from physical geometry')


def _validate_request(request, fixture, model, current_geometry, source_hash):
    # Parse every value before arithmetic: bool/NaN must never compare as a
    # sampled numeric state. No archive paths or commands come from this input.
    encoded(request)
    required = {'schema', 'request_id', 'winding', 'material_model', 'return_geometry',
                'source_basis_sha256', 'current_a', 'pm_offset_x_m', 'placement_acknowledged'}
    if set(request) != required or request.get('schema') != 'finite-dc-live-request-v1':
        raise UnsupportedDcRequest('Complete versioned live DC request required, with no unknown fields')
    if not isinstance(request['request_id'], str) or not 1 <= len(request['request_id']) <= 128:
        raise UnsupportedDcRequest('A bounded request identity is required')
    if request['placement_acknowledged'] is not True:
        raise UnsupportedDcRequest('Explicit physical material placement acknowledgement required; no automatic stack move')
    current, offset = request['current_a'], request['pm_offset_x_m']
    if type(current) not in [int, float] or current not in [0., .1, -.1, .5, -.5]:
        raise UnsupportedDcRequest('Only sampled loop currents0,+/-0.1,+/-0.5A are currently qualified; no interpolation')
    if type(offset) not in [int, float] or offset not in [0., .0001, -.0001]:
        raise UnsupportedDcRequest('Only explicit sampled PM offsets0,+/-100um are currently qualified')
    if request['source_basis_sha256'] != source_hash:
        raise UnsupportedDcRequest('Request selects a different or unqualified physical current basis')
    actual = geometry_descriptor(request['winding'])
    expected = geometry_descriptor(reference_snapshot(fixture))
    check_stack_settings(actual['sim'].get('backplane'), model)
    # Compare copper independently of the nominal UI stack representation only
    # AFTER its settings match the explicit material geometry/law.
    actual['sim']['backplane'] = expected['sim'].get('backplane')
    if encoded(actual) != encoded(expected):
        raise UnsupportedDcRequest('Actual winding/config/depth/network differs from the qualified case; qualification is required')
    if encoded(request['material_model']) != encoded(physical_model(posed_model(model, offset))):
        raise UnsupportedDcRequest('Actual material/PM geometry differs from the approved qualified placement; no repair applied')
    return_keys = ['return_path_m', 'return_width_m', 'return_thickness_m', 'drive_path_m']
    expected_return = {key: current_geometry[key] for key in return_keys}
    if encoded(request['return_geometry']) != encoded(expected_return):
        raise UnsupportedDcRequest('Declared finite return/drive geometry differs from the qualified source; no closure invented')
    digest = hashlib.sha256(encoded(request).encode()).hexdigest()
    return dict(status='eligible-for-recorded-geometry-live-recalculation-only', request_id=request['request_id'],
                request_sha256=digest, source_basis_sha256=source_hash, current_a=current, pm_offset_x_m=offset,
                scope='Eligibility only, not a magnetic result. Rebuild/check physical geometry and solve fresh; do not replay archived forces.')


def validate_request(request, fixture, model, current_geometry, source_hash):
    try:
        return _validate_request(request, fixture, model, current_geometry, source_hash)
    except UnsupportedDcRequest:
        raise
    except (KeyError, TypeError, IndexError, ValueError, ZeroDivisionError) as error:
        raise UnsupportedDcRequest('Malformed or unsupported actual DC geometry: '+str(error)) from error
