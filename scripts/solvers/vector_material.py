"""Reversible isotropic two-slope law in B, matching the existing H-law input.

Bs is saturation polarization, not a hard limit on total B. The differential
tensor follows from the full vector energy. No material parameter is fitted.
"""
import math

MU0=4e-7*math.pi


def energy_b(ng,b,mu,bsat):
    squared=ng.InnerProduct(b,b)
    if mu==1 or bsat is None:return squared/(2*MU0*mu)
    knee=bsat*mu/(mu-1);radius=ng.sqrt(ng.IfPos(squared,squared,1.))
    constant=knee*knee/(2*MU0*mu)-(knee-bsat)**2/(2*MU0)
    return ng.IfPos(squared-knee*knee,(radius-bsat)**2/(2*MU0)+constant,squared/(2*MU0*mu))


def h_b(ng,b,mu,bsat):
    if mu==1 or bsat is None:return b/(MU0*mu)
    squared=ng.InnerProduct(b,b);knee=bsat*mu/(mu-1)
    radius=ng.sqrt(ng.IfPos(squared,squared,1.))
    reluctivity=ng.IfPos(squared-knee*knee,(1-bsat/radius)/MU0,1/(MU0*mu))
    return reluctivity*b


def magnetization_b(ng,b,mu,bsat):
    return b/MU0-h_b(ng,b,mu,bsat)


def reduced_density(ng,reaction_b,source_b,mu,bsat):
    # Subtract only the analytic vacuum particular-field constant and its linear
    # cross term. This is the source transformation, not failed-floor subtraction.
    return energy_b(ng,source_b+reaction_b,mu,bsat)-ng.InnerProduct(source_b,reaction_b)/MU0-ng.InnerProduct(source_b,source_b)/(2*MU0)
