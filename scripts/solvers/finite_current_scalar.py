"""Independent H1 reaction-H formulation for prescribed finite static sources.

H_source carries all free current. The reaction is -grad(psi), so its curl is
zero everywhere including copper; no single-valued potential for H_source is
assumed. Across material interfaces this weak form enforces div(B)=0 and the
reaction has continuous tangential H. Outer psi=0 approximates infinity and
needs separate domain refinement. This shares source data, not magnetic DOFs,
with the reaction-B HCurl formulation. No independent current solve is claimed.
"""
from ngsolve_reduced import energy_density
from finite_current_zero_bias import magnetic_regions
from vector_material import MU0


def scalar_form(ng, space, mesh, model, source_b, rules):
    soft = magnetic_regions(model, mesh.GetMaterials())
    vacuum = sorted(set(mesh.GetMaterials())-{region['name'] for region in soft})
    gradient = ng.grad(space.TrialFunction())
    form = ng.BilinearForm(space, symmetric=True)
    form += ng.Variation(MU0*ng.InnerProduct(gradient, gradient)/2*ng.dx(
        definedon=mesh.Materials('|'.join(vacuum)), intrules=rules))
    for region in soft:
        density = MU0*energy_density(ng, gradient, source_b/MU0, region['mu_r'], region['bsat_t'])
        form += ng.Variation(density.Compile()*ng.dx(definedon=mesh.Materials(region['name']), intrules=rules))
    return form


def magnetization_h(ng, total_h, mu, bsat):
    if mu == 1:
        return ng.CoefficientFunction((0., 0., 0.))
    if bsat is None:
        return (mu-1)*total_h
    squared = ng.InnerProduct(total_h, total_h)
    knee = bsat/(MU0*(mu-1))
    radius = ng.sqrt(ng.IfPos(squared, squared, 1.))
    return ng.IfPos(squared-knee*knee, bsat/(MU0*radius), mu-1)*total_h
