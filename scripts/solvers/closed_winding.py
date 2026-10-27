"""Build a balanced two-phase saved winding with an explicit external return.

The return waypoints are a declared screening scenario, not recovered CAD.
Signed trace/via currents come from the independently reconstructed resistor
graph. No open phase is silently closed and no copper depth is changed.
"""
import numpy as np

from closed_wire_source import validate
from winding_oracle import edge_points,resistances,unit_currents


def build(fixture,positive,negative,translation,return_waypoints):
    if positive==negative:raise ValueError('Two distinct driven phases required')
    shift=np.asarray(translation,dtype=float);waypoints=np.asarray(return_waypoints,dtype=float)
    if shift.shape!=(3,) or waypoints.ndim!=2 or waypoints.shape[1]!=3 or len(waypoints)<1 or not np.isfinite(shift).all() or not np.isfinite(waypoints).all():
        raise ValueError('Explicit finite external-return waypoints required')
    segments=[];currents=[];terminals=[];stars=[];phase_data={}
    for phase,sign in [(positive,1.),(negative,-1.)]:
        matching=[n for n in fixture['networks'] if n['net']==phase]
        if len(matching)!=1:raise ValueError('Driven phase not uniquely present')
        network=matching[0]
        if len(network['terminal'])!=1 or len(network['star'])!=1:
            raise ValueError('This explicit return scenario requires one terminal and star per phase')
        resistance=resistances(network,fixture['sim'],fixture['drive'],fixture['geometry_hints'])
        shares,equivalent=unit_currents(network,resistance);nodes={}
        for edge,share in zip(network['edges'],shares):
            points=edge_points(edge,fixture['sim'],fixture['geometry_hints'])+shift
            for node,point in [(edge['a'],points[0]),(edge['b'],points[-1])]:
                if node in nodes and np.linalg.norm(point-nodes[node])>1e-11:raise ValueError('Inconsistent graph node positions')
                nodes[node]=point
            for a,b in zip(points[:-1],points[1:]):segments.append([a,b]);currents.append(sign*share)
        terminals.append(nodes[network['terminal'][0]]);stars.append(nodes[network['star'][0]])
        phase_data[phase]={'current_a':sign,'resistance_ohm':equivalent,'terminal_m':terminals[-1].tolist(),'star_m':stars[-1].tolist()}
    if np.linalg.norm(stars[0]-stars[1])>1e-11:raise ValueError('Separate star endpoints need explicit physical star connectivity')
    # Positive-phase current enters its terminal, passes through the common
    # star and exits the negative-phase terminal. Return runs negative to positive.
    path=np.vstack([terminals[1],waypoints,terminals[0]])
    for a,b in zip(path[:-1],path[1:]):
        if np.linalg.norm(a-b)<=1e-11:raise ValueError('Duplicate external-return waypoint')
        segments.append([a,b]);currents.append(1.)
    segments,currents,continuity=validate(segments,currents)
    return segments,currents,{'phase_data':phase_data,'maximum_endpoint_current_error_a':continuity,
        'return_path_m':path.tolist(),'scope':'Unit balanced line current. External return is an explicit scenario, not hardware routing; ideal off-wire DC filament fields only.'}
