"""Nonmagnetic conducting sphere in a uniform harmonic applied B, SI/peak.

For exp(i*omega*t), k^2=-i*omega*mu0*sigma and x=k*a. Matching the l=1
interior spherical-Bessel A_phi=C*j1(k*r)*sin(theta) to the vacuum field gives
C=3*B0*a/(2*x*j0(x)) and m=-2*pi*a^3*B0/mu0 * (1-3/x^2+3*cot(x)/x).
Mean absorbed power is -omega*Im(m*conj(B0))/2. The independent volume-loss
function integrates the interior electric field rather than using that dipole.
No permeability, geometry or force/loss constant is fitted to a solver.
"""
import cmath
import math

import numpy as np
from scipy.integrate import quad
from scipy.special import spherical_jn

MU0=4e-7*math.pi


def inputs(radius,sigma,frequency,peak_b):
    if not np.isfinite([radius,sigma,frequency,peak_b]).all() or min(radius,sigma,frequency,peak_b)<=0:
        raise ValueError('Positive finite radius, conductivity, frequency and peak B required')
    omega=2*math.pi*frequency
    return omega,cmath.sqrt(-1j*omega*MU0*sigma)*radius


def dipole_loss(radius,sigma,frequency,peak_b):
    omega,x=inputs(radius,sigma,frequency,peak_b)
    # Cancellation-free low-frequency form, from the cotangent series.
    if abs(x)<.1:
        response=-x*x/15-2*x**4/315-x**6/1575-2*x**8/31185
    else:response=1-3/(x*x)+3/(x*cmath.tan(x))
    moment=-2*math.pi*radius**3*peak_b/MU0*response
    return float(-omega*moment.imag*peak_b/2)


def volume_loss(radius,sigma,frequency,peak_b):
    omega,x=inputs(radius,sigma,frequency,peak_b)
    coefficient=3*peak_b*radius/(2*x*spherical_jn(0,x))
    integral,error=quad(lambda s:abs(spherical_jn(1,x*s))**2*s*s,0.,1.,epsabs=1e-13,epsrel=1e-11)
    return float(4*math.pi/3*sigma*omega**2*abs(coefficient)**2*radius**3*integral)


def weak_loss(radius,sigma,frequency,peak_b):
    omega,_=inputs(radius,sigma,frequency,peak_b)
    return math.pi*sigma*omega**2*peak_b**2*radius**5/15
