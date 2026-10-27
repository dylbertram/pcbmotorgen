"""Reciprocal PM linkage of a verified closed prescribed-current wire circuit.

Integrates fixed PM polarization dotted with the unit-current wire B over each
physical PM volume. SI output Wb per unit circuit ampere. This is the free-space
PM linkage, not copper self inductance or nonlinear material linkage. Separate
volume-order and position-difference controls are required by callers.
"""
import numpy as np
from numpy.polynomial.legendre import leggauss

from closed_wire_source import fields,validate,MU0


def linkage(magnets,segments,currents,degree):
    if type(degree) is not int or not 2<=degree<=64:raise ValueError('PM volume quadrature degree must be in2..64')
    segments,currents,_=validate(segments,currents)
    abscissas,weights=leggauss(degree);u,v,w=np.meshgrid(abscissas,abscissas,abscissas,indexing='ij')
    unit=np.column_stack([u.ravel(),v.ravel(),w.ravel()]);product=np.einsum('i,j,k->ijk',weights,weights,weights).ravel()
    total=0.
    for magnet in magnets:
        origin=np.asarray(magnet['origin_m']);size=np.asarray(magnet['size_m']);polarization=np.asarray(magnet['polarization_t'])
        if origin.shape!=(3,) or size.shape!=(3,) or polarization.shape!=(3,) or not np.isfinite([origin,size,polarization]).all() or np.min(size)<=0:
            raise ValueError('Invalid fixed-remanence PM volume')
        points=origin+size/2+unit*size/2;quadrature_weights=product*np.prod(size)/8
        for first in range(0,len(points),4096):
            magnetic,_=fields(points[first:first+4096],segments,currents)
            total+=float(np.sum(quadrature_weights[first:first+4096]*(magnetic@polarization))/MU0)
    if not np.isfinite(total):raise ValueError('Nonfinite reciprocal PM linkage')
    return total


def position_gradient(magnets,segments,currents,degree,delta):
    if not np.isfinite(delta) or delta<=0:raise ValueError('Positive finite PM-position difference required')
    result=[]
    for axis in range(3):
        values=[]
        for sign in [1,-1]:
            offset=sign*delta*np.eye(3)[axis]
            moving=[dict(m,origin_m=(np.asarray(m['origin_m'])+offset).tolist()) for m in magnets]
            values.append(linkage(moving,segments,currents,degree))
        result.append((values[0]-values[1])/(2*delta))
    return np.array(result)
