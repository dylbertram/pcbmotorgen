"""Closed prescribed-current polyline sources, SI, without radius fitting.

Straight-segment Biot-Savart B and Coulomb A. These ideal filament kernels are
valid off the source, not an air self-inductance/skin model. Current continuity
is checked at geometric endpoints before a source can enter a material solve.
External return paths must be explicit; open terminal injections are rejected.
"""
import math

import numpy as np

MU0=4e-7*math.pi


def validate(segments,currents,coordinate_tolerance=1e-11,current_tolerance=1e-9):
    segments=np.asarray(segments,dtype=float);currents=np.asarray(currents,dtype=float)
    if segments.ndim!=3 or segments.shape[1:]!=(2,3) or currents.shape!=(len(segments),) or not np.isfinite(segments).all() or not np.isfinite(currents).all():
        raise ValueError('Invalid prescribed wire geometry/current')
    if coordinate_tolerance<=0 or current_tolerance<=0:raise ValueError('Positive continuity tolerances required')
    if np.any(np.linalg.norm(segments[:,1]-segments[:,0],axis=1)<=coordinate_tolerance):raise ValueError('Zero-length source segment')
    balance={}
    for (a,b),current in zip(segments,currents):
        for point,sign in [(a,1.),(b,-1.)]:
            key=tuple(np.rint(point/coordinate_tolerance).astype(np.int64))
            balance[key]=balance.get(key,0.)+sign*current
    maximum=max(map(abs,balance.values()),default=0.)
    if maximum>current_tolerance:raise ValueError('Open current source: explicit terminal/return closure required')
    return segments,currents,maximum


def fields(points,segments,currents):
    segments,currents,_=validate(segments,currents)
    points=np.asarray(points,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Invalid field observations')
    bfield=np.zeros_like(points);potential=np.zeros_like(points)
    for (a,b),current in zip(segments,currents):
        if current==0:continue
        vector=b-a;length=float(np.linalg.norm(vector));unit=vector/length
        first=points-a;last=points-b;s=first@unit;t=s-length
        perpendicular=first-s[:,None]*unit;rho2=np.sum(perpendicular*perpendicular,axis=1)
        r0=np.linalg.norm(first,axis=1);r1=np.linalg.norm(last,axis=1)
        collinear=rho2==0
        if np.any((r0==0)|(r1==0)|(collinear&(s>=0)&(s<=length))):raise ValueError('Filament self-field is singular; supply physical finite cross-section/clearance')
        active=~collinear
        factor=np.zeros(len(points));factor[active]=(s[active]/r0[active]-t[active]/r1[active])/rho2[active]
        # Outside the segment's axial interval, the difference above loses
        # precision near the extended line. This algebraically equivalent
        # endpoint expression avoids subtracting nearly identical cosines.
        dot=np.sum(first*last,axis=1);outside=dot>0
        factor[outside]=length*(r0[outside]+r1[outside])/(r0[outside]*r1[outside]*(r0[outside]*r1[outside]+dot[outside]))
        bfield+=MU0*current/(4*math.pi)*np.cross(unit,perpendicular)*factor[:,None]
        integral=np.zeros(len(points));rho=np.sqrt(rho2[active])
        integral[active]=np.arcsinh(s[active]/rho)-np.arcsinh(t[active]/rho)
        integral[collinear]=abs(np.log(r0[collinear]/r1[collinear]))
        potential+=MU0*current/(4*math.pi)*integral[:,None]*unit
    return bfield,potential


def coefficient(ng,segments,currents):
    """Compiled off-wire source for verified closed segment sets only."""
    segments,currents,_=validate(segments,currents)
    bfield=ng.CoefficientFunction((0.,0.,0.));potential=ng.CoefficientFunction((0.,0.,0.))
    position=ng.CoefficientFunction((ng.x,ng.y,ng.z))
    for (a,b),current in zip(segments,currents):
        if current==0:continue
        vector=b-a;length=float(np.linalg.norm(vector));u=vector/length;unit=ng.CoefficientFunction(tuple(u))
        first=position-ng.CoefficientFunction(tuple(a));last=position-ng.CoefficientFunction(tuple(b))
        s=ng.InnerProduct(first,unit);t=s-length;perpendicular=first-s*unit
        rho2=ng.InnerProduct(perpendicular,perpendicular);r0=ng.sqrt(ng.InnerProduct(first,first));r1=ng.sqrt(ng.InnerProduct(last,last))
        cross=ng.CoefficientFunction((u[1]*perpendicular[2]-u[2]*perpendicular[1],u[2]*perpendicular[0]-u[0]*perpendicular[2],u[0]*perpendicular[1]-u[1]*perpendicular[0]))
        safe_rho2=ng.IfPos(rho2,rho2,1.)
        dot=ng.InnerProduct(first,last)
        safe_dot=ng.IfPos(dot,dot,0.)
        outside=length*(r0+r1)/(r0*r1*(r0*r1+safe_dot))
        inside=(s/r0-t/r1)/safe_rho2
        bfield+=MU0*current/(4*math.pi)*cross*ng.IfPos(dot,outside,inside)
        # Symmetric length form also handles collinear observations beyond
        # either endpoint without the 0/0 of log((s+r0)/(t+r1)).
        potential+=MU0*current/(4*math.pi)*unit*ng.log((r0+r1+length)/(r0+r1-length))
    return bfield.Compile(),potential.Compile()
