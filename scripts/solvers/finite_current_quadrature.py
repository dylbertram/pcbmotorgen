"""Physical-point storage for finite-source values at one exact material rule.

Not a spatial interpolator. Restore/check mesh/source hashes separately, use the
returned rules in every consuming form, and never use this CF off its rule.
"""
from dataclasses import dataclass

import numpy as np

from quadrature_source import rule_table


@dataclass
class Layout:
    space: object
    rules: object
    degree: int
    regions: str
    points: np.ndarray
    element_numbers: np.ndarray
    blocks: list


def check_rules(ng, layout, degree):
    if degree != layout.degree:
        raise ValueError('Finite-source point cache cannot be consumed at a different rule')
    for element_type in layout.rules:
        if not np.array_equal(rule_table(layout.rules[element_type]), rule_table(ng.IntegrationRule(element_type, degree))):
            raise ValueError('Finite-source storage/consuming quadrature rules differ')


def material_layout(ng, mesh, regions, degree):
    if type(degree) is not int or degree < 2 or degree % 2:
        raise ValueError('Explicit positive even material integration degree required')
    space = ng.comp.IntegrationRuleSpace(mesh, order=degree//2, definedon=mesh.Materials(regions))
    rules = space.GetIntegrationRules()
    coordinate = ng.CoefficientFunction((ng.x, ng.y, ng.z))
    points, element_numbers, blocks = [], [], []
    offset = 0
    used = set()
    for element in mesh.Elements():
        dofs = np.asarray(space.GetDofNrs(element), dtype=int)
        if not len(dofs) or np.all(dofs < 0):
            continue
        if np.any(dofs < 0):
            raise ValueError('Partially defined source integration element')
        used.add(element.type)
        mapped = mesh.GetTrafo(element)(rules[element.type])
        coordinates = np.asarray(coordinate(mapped)).reshape(-1, 3)
        if coordinates.shape != (len(dofs), 3) or not np.isfinite(coordinates).all():
            raise ValueError('Invalid physical material quadrature layout')
        points.append(coordinates)
        element_numbers.extend([element.nr]*len(dofs))
        blocks.append((element.nr, dofs, offset, offset+len(dofs)))
        offset += len(dofs)
    if not points:
        raise ValueError('No actual material quadrature points')
    layout = Layout(space, {t: rules[t] for t in used}, degree, regions, np.concatenate(points), np.asarray(element_numbers), blocks)
    check_rules(ng, layout, degree)
    return layout


def source_components(ng, mesh, layout, values):
    values = np.asarray(values, dtype=float)
    if values.shape != layout.points.shape or not np.isfinite(values).all():
        raise ValueError('Finite-source values must match every physical quadrature point')
    check_rules(ng, layout, layout.degree)
    components = [ng.GridFunction(layout.space) for _ in range(3)]
    for _, dofs, first, last in layout.blocks:
        for axis, component in enumerate(components):
            component.vec.FV().NumPy()[dofs] = values[first:last, axis]
    coefficient = ng.CoefficientFunction(tuple(components))
    # Do not call coefficient(mapped): the Python MeshPoint array loses the
    # integration-point index needed by IntegrationRuleSpace. Native integrators
    # retain that index; point evaluation can corrupt memory in NGSolve 6.2.2608.
    maximum = 0.
    measures = ng.dx(definedon=mesh.Materials(layout.regions), intrules=layout.rules)
    probes = [ng.CoefficientFunction(1.), ng.x, ng.y, ng.z]
    integrals = [[np.asarray(ng.Integrate(component*probe*measures, mesh, element_wise=True))
                  for probe in probes] for component in components]
    squares = [np.asarray(ng.Integrate(component*component*measures, mesh, element_wise=True))
               for component in components]
    xyz = ng.CoefficientFunction((ng.x, ng.y, ng.z))
    corners = ng.IntegrationRule(points=[(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)], weights=[1.]*4)
    for number, dofs, first, last in layout.blocks:
        element = mesh[ng.ElementId(ng.VOL, int(number))]
        if element.type != ng.ET.TET:
            raise ValueError('Source storage controls require affine tetrahedra')
        rule = layout.rules[element.type]
        vertices = np.asarray(xyz(mesh.GetTrafo(element)(corners))).reshape(4, 3)
        matrix = vertices[1:]-vertices[0]
        local = np.array([point.point[:3] for point in rule])
        if np.max(abs(layout.points[first:last]-(vertices[0]+local@matrix))) > 1e-12:
            raise ValueError('Source storage controls require physical curved-cell Jacobians')
        weights = np.array([point.weight for point in rule])*abs(float(np.linalg.det(matrix)))
        samples = np.column_stack([np.ones(last-first), layout.points[first:last]])
        for axis, component in enumerate(components):
            actual = component.vec.FV().NumPy()[dofs]
            if not np.array_equal(actual, values[first:last, axis]):
                raise ValueError('Source storage changed supplied point values')
            expected = weights@((values[first:last, axis, None])*samples)
            observed = np.array([a[int(number)] for a in integrals[axis]])
            # Signed moments may cancel. Normalize each by its unsigned moment.
            scale = np.maximum(weights@(abs(values[first:last, axis, None]*samples)), 1e-300)
            maximum = max(maximum, float(np.max(abs(observed-expected)/scale)))
            expected_square = float(weights@(values[first:last, axis]**2))
            maximum = max(maximum, abs(float(squares[axis][int(number)])-expected_square)/max(expected_square, 1e-300))
    if maximum > 1e-13:
        raise ValueError('IR scalar storage does not reproduce the supplied physical source')
    return coefficient, components, {'kind': 'finite-source-at-exact-declared-physical-quadrature-only',
        'points': len(values), 'degree': layout.degree, 'regions': layout.regions,
        'maximum_relative_storage_error': maximum, 'storage_control': 'exact DOF readback and native per-element constant/coordinate/squared moments',
        'off_rule_evaluation': 'forbidden, including Python MeshPoint-array evaluation at rule coordinates'}


def weighted_rule_values(ng, mesh, layout, field, region):
    """Read field*dV by native IR test functions, never Python point evaluation.

    The delta basis retains the declared integration-point indices and physical
    Jacobian weights. This is quadrature extraction, not a spatial projection.
    """
    check_rules(ng, layout, layout.degree)
    if field.dim != 3 or region not in layout.regions.split('|'):
        raise ValueError('Three-component field and an explicit cached region required')
    test = layout.space.TestFunction()
    vectors = []
    for axis in range(3):
        form = ng.LinearForm(layout.space)
        form += field[axis]*test*ng.dx(definedon=mesh.Materials(region), intrules=layout.rules)
        form.Assemble()
        vectors.append(form.vec.FV().NumPy().copy())
    points, values = [], []
    for number, dofs, first, last in layout.blocks:
        if mesh[ng.ElementId(ng.VOL, int(number))].mat != region:
            continue
        points.append(layout.points[first:last])
        values.append(np.column_stack([v[dofs] for v in vectors]))
    if not points or not np.isfinite(np.concatenate(values)).all():
        raise ValueError('Missing/nonfinite native material quadrature values')
    return np.concatenate(points), np.concatenate(values)
