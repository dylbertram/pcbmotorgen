"""Exact circular trace CAD for offline qualification, never chord replacement.

The electrical graph may retain a chord sampling for its resistance reference;
that approximation is reported separately against analytical arc length. The
current-carrying solid uses OCCT circular edges and the actual copper thickness.
"""
import math

import numpy as np


def parameters(primitive):
    if set(primitive) != {'start', 'mid', 'end'}:
        raise ValueError('Complete three-point circular copper primitive required')
    points = np.asarray([primitive[key] for key in ['start', 'mid', 'end']], dtype=float)
    if points.shape != (3, 2) or not np.isfinite(points).all():
        raise ValueError('Finite planar circular copper points required')
    a, b = points[1:]-points[0]
    cross = a[0]*b[1]-a[1]*b[0]
    if np.linalg.norm(a)*np.linalg.norm(b) == 0 or abs(cross) <= 1e-12*np.linalg.norm(a)*np.linalg.norm(b):
        raise ValueError('Degenerate circular copper; no straight/chord repair permitted')
    centre = points[0]+np.linalg.solve(2*np.vstack([a, b]), np.array([a@a, b@b]))
    radius = float(np.linalg.norm(points[0]-centre))
    angles = np.arctan2((points-centre)[:, 1], (points-centre)[:, 0])
    ccw_mid, ccw_end = [float(value) for value in (angles[1:]-angles[0]) % (2*math.pi)]
    sweep = ccw_end if ccw_mid < ccw_end else ccw_end-2*math.pi
    if radius <= 0 or not 0 < abs(sweep) < 2*math.pi:
        raise ValueError('Non-simple circular copper primitive')
    return dict(centre_m=centre.tolist(), radius_m=radius, sweep_rad=sweep, length_m=radius*abs(sweep))


def solid(primitive, z, width, thickness):
    from netgen.occ import Pnt, Vec, Dir, Segment, ArcOfCircle, Wire, Face, Cylinder
    spec = parameters(primitive)
    if not np.isfinite([z, width, thickness]).all() or min(width, thickness) <= 0 or spec['radius_m'] <= width/2:
        raise ValueError('Finite copper width/thickness and positive inner arc radius required')
    points = np.asarray([primitive[key] for key in ['start', 'mid', 'end']])
    centre, radius = np.asarray(spec['centre_m']), spec['radius_m']
    radial = (points-centre)/radius
    low = z-thickness/2
    outer = [Pnt(float(p[0]), float(p[1]), low) for p in centre+(radius+width/2)*radial]
    inner = [Pnt(float(p[0]), float(p[1]), low) for p in centre+(radius-width/2)*radial]
    sector = Face(Wire([ArcOfCircle(*outer), Segment(outer[-1], inner[-1]),
                        ArcOfCircle(*reversed(inner)), Segment(inner[0], outer[0])])).Extrude(Vec(0, 0, thickness))
    # Same round-ended finite stroke convention as straight saved traces. No
    # intermediate chord joints or invented source radius enter this solid.
    for point in [points[0], points[-1]]:
        sector = sector+Cylinder(Pnt(float(point[0]), float(point[1]), low), Dir(0, 0, 1), width/2, thickness)
    return sector


def chord_control(geometry):
    spec = parameters(geometry['circular_arc_m'])
    points = np.asarray(geometry['points_m'], dtype=float)
    primitive = geometry['circular_arc_m']
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
        raise ValueError('Declared circular graph sampling required')
    if not np.array_equal(points[0], primitive['start']) or not np.array_equal(points[-1], primitive['end']):
        raise ValueError('Graph circular endpoints differ from actual CAD')
    radial_error = float(np.max(abs(np.linalg.norm(points-np.asarray(spec['centre_m']), axis=1)-spec['radius_m'])))
    if radial_error > 1e-10*spec['radius_m']:
        raise ValueError('Graph circular samples are off the actual CAD circle')
    relative = points-np.asarray(spec['centre_m'])
    angles = np.unwrap(np.arctan2(relative[:,1],relative[:,0]))
    if (np.any(np.diff(angles)*spec['sweep_rad'] <= 0) or
        abs((angles[-1]-angles[0])-spec['sweep_rad']) > 1e-10):
        raise ValueError('Graph circular sampling takes a different direction or sweep')
    length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
    error = abs(length/spec['length_m']-1)
    return dict(**spec, graph_chord_length_m=length, relative_length_difference=error, limit=.02, passed=error <= .02)


def section_plane(primitive,z,width):
    """Exact tangent-normal section at the saved arc midpoint, not a chord."""
    spec=parameters(primitive);mid=np.asarray(primitive['mid'],dtype=float)
    radius=width*.75
    if min(np.linalg.norm(mid-np.asarray(primitive[key])) for key in ['start','end']) <= math.sqrt(2)*radius+width/2:
        raise ValueError('Native circular section window is not isolated from end-cap junctions')
    radial=(mid-np.asarray(spec['centre_m']))/spec['radius_m'];sign=math.copysign(1.,spec['sweep_rad'])
    return dict(centre=[float(mid[0]),float(mid[1]),float(z)],normal=[float(-sign*radial[1]),float(sign*radial[0]),0.],radius=radius)
