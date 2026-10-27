"""Exact fixed-source values at one explicitly identified integration rule.

Not a field interpolator: this cache MUST only enter forms using its exact
quadrature rule. Off-rule force/field postprocessing must use the analytical
source. Scalar IR gridfunctions avoid vector-layout ambiguities in the pinned
NGSolve IntegrationRuleSpace. No GridFunction.Set projection is used.
"""
import time

import numpy as np


def rule_table(rule):
    return np.array([list(point.point)+[point.weight] for point in rule])


def fixed_source(ng,mesh,source,regions,degree):
    if type(degree) is not int or degree<2 or degree%2:raise ValueError('Positive even integration degree required')
    if source.dim!=3:raise ValueError('Expected a fixed three-component source')
    started=time.monotonic();space=ng.comp.IntegrationRuleSpace(mesh,order=degree//2,definedon=mesh.Materials(regions))
    rules=space.GetIntegrationRules()
    used=set(element.type for element in mesh.Elements())
    for element_type in used:
        first=rule_table(rules[element_type]);second=rule_table(ng.IntegrationRule(element_type,degree))
        if first.shape!=second.shape or not np.array_equal(first,second):raise ValueError('IR storage and assembled integration rules differ')
    components=[ng.GridFunction(space) for _ in range(3)];points=0;elements=0
    for element in mesh.Elements():
        dofs=np.array(space.GetDofNrs(element),dtype=int)
        if not len(dofs) or np.all(dofs<0):continue
        if np.any(dofs<0):raise ValueError('Partially defined integration-point source element')
        mapped=mesh.GetTrafo(element)(rules[element.type]);values=np.asarray(source(mapped)).reshape(-1,3)
        if values.shape!=(len(dofs),3) or not np.isfinite(values).all():raise ValueError('Invalid integration-point source values')
        for axis,component in enumerate(components):component.vec.FV().NumPy()[dofs]=values[:,axis]
        points+=len(dofs);elements+=1
    if points==0:raise ValueError('No defined source integration points')
    cached=ng.CoefficientFunction(tuple(components));difference=cached-source
    squared=float(ng.Integrate(ng.InnerProduct(difference,difference),mesh,definedon=mesh.Materials(regions),order=degree))
    norm=float(ng.Integrate(ng.InnerProduct(source,source),mesh,definedon=mesh.Materials(regions),order=degree))
    relative=np.sqrt(max(0.,squared)/max(norm,1e-300))
    if not np.isfinite(relative) or relative>1e-13:raise ValueError('Fixed source cache does not reproduce the exact assembled quadrature')
    metadata={'kind':'exact-fixed-source-at-declared-quadrature-only','degree':degree,'regions':regions,'elements':elements,
        'points':points,'relative_source_l2_error':float(relative),'seconds':time.monotonic()-started,
        'off_rule_evaluation':'forbidden; retain analytical source for postprocessing'}
    return cached,components,rules,metadata


def update_source(ng,mesh,source,components,rules,regions,degree):
    """Update existing point storage between prescribed source poses.

    The nonlinear reaction remains a solver unknown, never a cached source.
    Callers must update every prescribed pose before assembly and retain the
    analytical source for off-rule fields and endpoint energy accounting.
    """
    if type(degree) is not int or degree<2 or degree%2 or len(components)!=3 or source.dim!=3:
        raise ValueError('Invalid exact source update')
    started=time.monotonic();space=components[0].space;stored_rules=space.GetIntegrationRules()
    for element_type in set(element.type for element in mesh.Elements()):
        if not np.array_equal(rule_table(rules[element_type]),rule_table(stored_rules[element_type])) or not np.array_equal(rule_table(rules[element_type]),rule_table(ng.IntegrationRule(element_type,degree))):
            raise ValueError('Updated source requires the exact stored/assembled integration rule')
    points=0
    for element in mesh.Elements():
        dofs=np.array(space.GetDofNrs(element),dtype=int)
        if not len(dofs) or np.all(dofs<0):continue
        if np.any(dofs<0):raise ValueError('Partially defined updated source element')
        mapped=mesh.GetTrafo(element)(rules[element.type]);values=np.asarray(source(mapped)).reshape(-1,3)
        if values.shape!=(len(dofs),3) or not np.isfinite(values).all():raise ValueError('Invalid updated source values')
        for axis,component in enumerate(components):component.vec.FV().NumPy()[dofs]=values[:,axis]
        points+=len(dofs)
    if points==0:raise ValueError('No updated source integration points')
    cached=ng.CoefficientFunction(tuple(components));difference=cached-source
    squared=float(ng.Integrate(ng.InnerProduct(difference,difference),mesh,definedon=mesh.Materials(regions),order=degree))
    norm=float(ng.Integrate(ng.InnerProduct(source,source),mesh,definedon=mesh.Materials(regions),order=degree))
    relative=np.sqrt(max(0.,squared)/max(norm,1e-300))
    if not np.isfinite(relative) or relative>1e-13:raise ValueError('Updated source differs from analytical quadrature values')
    return {'points':points,'relative_source_l2_error':float(relative),'seconds':time.monotonic()-started}
