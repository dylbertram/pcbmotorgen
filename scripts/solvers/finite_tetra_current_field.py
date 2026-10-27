"""Exterior Biot-Savart field of constant or affine RT0 tetrahedron currents.

For each cell, Gauss' theorem converts the volume gradient of 1/R to outward
face integrals. Triangle potentials use edge logarithms and signed solid angle.
No centreline substitution, source radius, softening or fitted constant is used.
Callers must independently verify their cell-current representation, source
continuity, geometry, quadrature/source refinement and magnetic observables.
This kernel alone is not a qualified winding source or coupled-field solver.
"""
import numpy as np

MU0_OVER_4PI = 1e-7
FACES = [(1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1)]


def _triangle_potential(points, triangles):
    first, second, third = [triangles[:, i] for i in range(3)]
    normal = np.cross(second-first, third-first)
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    vectors = triangles[None, :, :, :]-points[:, None, None, :]
    radii = np.linalg.norm(vectors, axis=3)
    potential = np.zeros((len(points), len(triangles)))
    for i, j in [(0, 1), (1, 2), (2, 0)]:
        edge = triangles[:, j]-triangles[:, i]
        length = np.linalg.norm(edge, axis=1)
        outward = np.cross(edge/length[:, None], normal)
        distance = np.einsum('pni,ni->pn', vectors[:, :, i], outward)
        denominator = radii[:, :, i]+radii[:, :, j]-length[None, :]
        if np.any(denominator <= 0):
            raise ValueError('On-edge or unresolved triangle potential; no source softening applied')
        potential += distance*np.log1p(2*length[None, :]/denominator)
    a, b, c = [vectors[:, :, i] for i in range(3)]
    determinant = np.einsum('pni,pni->pn', a, np.cross(b, c))
    denominator = (np.prod(radii, axis=2)+np.einsum('pni,pni->pn', a, b)*radii[:, :, 2]
                   +np.einsum('pni,pni->pn', b, c)*radii[:, :, 0]
                   +np.einsum('pni,pni->pn', c, a)*radii[:, :, 1])
    solid_angle = -2*np.arctan2(determinant, denominator)
    height = -np.einsum('pni,ni->pn', a, normal)
    potential -= height*solid_angle
    if not np.isfinite(potential).all() or np.any(potential < 0):
        raise ValueError('Nonfinite/negative triangle integral; exterior evaluation unresolved')
    return potential, normal


def _reject_interior(points, cells):
    low, high = cells.min(axis=1), cells.max(axis=1)
    for point in points:
        candidates = cells[np.all((point >= low) & (point <= high), axis=1)]
        if not len(candidates):
            continue
        matrix = np.swapaxes(candidates[:, 1:]-candidates[:, :1], 1, 2)
        coordinates = np.linalg.solve(matrix, np.broadcast_to(point, candidates[:, 0].shape)-candidates[:, 0])
        # Numerical barycentric ownership tolerance, not a physical radius.
        if np.any(np.all(coordinates >= -1e-12, axis=1) & (coordinates.sum(axis=1) <= 1+1e-12)):
            raise ValueError('Exterior current kernel refuses observations inside/on copper')


def tetrahedron_field(points, tetrahedra, current_density, batch_cells=2048, batch_points=16, radial_slope=None):
    """Integrate J(y)=current_density+slope*(y-cell_centroid) exactly.

    RT0 on an affine tetrahedron has precisely this form. The radial term can
    be factored as slope*(observation-centroid) before crossing the volume
    gradient, since (y-centroid) cross (r-y)=(r-centroid) cross (r-y).
    This is an algebraic identity, not a current source outside the conductor.
    """
    points = np.asarray(points, dtype=float)
    cells = np.asarray(tetrahedra, dtype=float)
    current = np.asarray(current_density, dtype=float)
    slope = np.zeros(len(cells)) if radial_slope is None else np.asarray(radial_slope, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (3,) or cells.ndim != 3 or cells.shape[1:] != (4, 3) or current.shape != (len(cells), 3):
        raise ValueError('Need physical observation/tetrahedron/constant-current arrays')
    if slope.shape != (len(cells),) or not all(np.isfinite(x).all() for x in [points, cells, current, slope]):
        raise ValueError('Nonfinite current geometry or observations')
    if any(type(x) is not int or x < 1 for x in [batch_cells, batch_points]):
        raise ValueError('Positive integral batch limits required')
    result = np.zeros_like(points)
    for begin in range(0, len(cells), batch_cells):
        part = cells[begin:begin+batch_cells].copy()
        density = current[begin:begin+batch_cells]
        part_slope = slope[begin:begin+batch_cells]
        centres = part.mean(axis=1)
        determinant = np.linalg.det(part[:, 1:]-part[:, :1])
        if np.any(determinant == 0) or not np.isfinite(determinant).all():
            raise ValueError('Degenerate tetrahedron cannot carry a finite current source')
        reverse = determinant < 0
        part[reverse, 1:3] = part[reverse, 1:3][:, ::-1]
        for first in range(0, len(points), batch_points):
            observations = points[first:first+batch_points]
            _reject_interior(observations, part)
            gradient = np.zeros((len(observations), len(part), 3))
            for face in FACES:
                potential, normal = _triangle_potential(observations, part[:, face, :])
                gradient += potential[:, :, None]*normal[None, :, :]
            algebraic_current = density[None, :, :]+part_slope[None, :, None]*(observations[:, None, :]-centres[None, :, :])
            result[first:first+len(observations)] += MU0_OVER_4PI*np.cross(algebraic_current, gradient).sum(axis=1)
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite exterior finite-current field')
    return result
