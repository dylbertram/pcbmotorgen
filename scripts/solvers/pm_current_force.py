"""PM force from the free-space field of volume-current quadrature sources.

Use F_i=integral_PM(M_z*d_i B_current,z)dV, evaluated on opposite PM faces.
The rectangular face integrals of the Biot-Savart kernel are analytical. This
is a separate force operator, not the negative of a conductor-force result.
It assumes fixed axial magnetization, mu_r=1 PMs and source currents below them.
Current sources are J*dV in A*m. No PM self-field or failed-force floor enters.
"""
from concurrent.futures import ThreadPoolExecutor
import math

import numpy as np
from numpy.polynomial.legendre import leggauss

MU0=4e-7*math.pi


def rectangle_kernel(points,origin,size,axis,side):
    """Integral_face (r-source)/|r-source|^3 dS for every source point."""
    others=[i for i in range(3) if i!=axis];u_axis,v_axis=others
    d=origin[axis]+side*size[axis]-points[:,axis]
    result=np.zeros_like(points,dtype=float)
    for i in range(2):
        for j in range(2):
            u=origin[u_axis]+i*size[u_axis]-points[:,u_axis]
            v=origin[v_axis]+j*size[v_axis]-points[:,v_axis]
            radius=np.sqrt(d*d+u*u+v*v);sign=(-1)**(i+j)
            if np.any(radius==0) or np.any(v+radius<=0) or np.any(u+radius<=0):
                raise ValueError('Singular current/PM face interaction')
            result[:,axis]+=sign*np.arctan2(u*v,d*radius)
            result[:,u_axis]-=sign*np.log(v+radius)
            result[:,v_axis]-=sign*np.log(u+radius)
    # The signed solid angle is defined modulo 4*pi, not a force correction.
    result[:,axis]=(result[:,axis]+2*math.pi)%(4*math.pi)-2*math.pi
    return result


def magnet_force(magnet,points,current_weights):
    if magnet['polarization_t'][:2]!=[0,0]:raise ValueError('Only fixed axial PMs are supported')
    origin=np.asarray(magnet['origin_m'],dtype=float);size=np.asarray(magnet['size_m'],dtype=float)
    if np.any(points[:,2]>=origin[2]):raise ValueError('This force audit requires currents below the PMs')
    force=np.zeros(3)
    for axis in range(3):
        for side in range(2):
            kernel=rectangle_kernel(points,origin,size,axis,side)
            integral=np.sum(current_weights[:,0]*kernel[:,1]-current_weights[:,1]*kernel[:,0])
            force[axis]+=(2*side-1)*magnet['polarization_t'][2]/(4*math.pi)*integral
    return force


def array_force(magnets,points,current_weights,workers=1):
    points=np.asarray(points,dtype=float);weights=np.asarray(current_weights,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or weights.shape!=points.shape or not np.isfinite([points,weights]).all():
        raise ValueError('Invalid volume-current sources')
    if workers>1:
        with ThreadPoolExecutor(max_workers=min(workers,len(magnets))) as pool:
            forces=list(pool.map(lambda magnet:magnet_force(magnet,points,weights),magnets))
    else:forces=[magnet_force(m,points,weights) for m in magnets]
    return np.asarray(forces)


def biot_z(observations,points,current_weights):
    result=np.zeros(len(observations))
    for start in range(0,len(points),4096):
        source=points[start:start+4096];weight=current_weights[start:start+4096]
        dx=observations[:,None,0]-source[None,:,0]
        dy=observations[:,None,1]-source[None,:,1]
        dz=observations[:,None,2]-source[None,:,2]
        squared=dx*dx+dy*dy+dz*dz
        if np.any(squared==0):raise ValueError('Overlapping current and observation')
        result+=np.sum((weight[None,:,0]*dy-weight[None,:,1]*dx)/(squared*np.sqrt(squared)),axis=1)*MU0/(4*math.pi)
    return result


def numerical_face_force(magnet,points,current_weights,n=12):
    """Independent numerical face integration for checking the primitives."""
    nodes,weights=leggauss(n);origin=np.asarray(magnet['origin_m']);size=np.asarray(magnet['size_m'])
    force=np.zeros(3)
    for axis in range(3):
        j,k=[i for i in range(3) if i!=axis]
        u,v=np.meshgrid((nodes+1)/2,(nodes+1)/2,indexing='ij')
        area=np.outer(weights,weights).ravel()*size[j]*size[k]/4
        for side in range(2):
            obs=np.tile(origin,(n*n,1));obs[:,axis]+=side*size[axis]
            obs[:,j]+=u.ravel()*size[j];obs[:,k]+=v.ravel()*size[k]
            force[axis]+=(2*side-1)*magnet['polarization_t'][2]/MU0*float(area@biot_z(obs,points,current_weights))
    return force


def magnetization_force(magnet,points,moment_weights,delta=1e-7):
    """PM force due to volume dipoles M*dV, via a refined kernel derivative.

    Integral_face B_M,z = mu0/(4*pi) * sum_j M_j*d_source_z(I_j).
    The current-source face kernel is reused, but no current or conductor force
    enters this dipole source calculation.
    """
    if magnet['polarization_t'][:2]!=[0,0]:raise ValueError('Only axial receiver PMs are supported')
    origin=np.asarray(magnet['origin_m'],dtype=float);size=np.asarray(magnet['size_m'],dtype=float)
    if delta<=0 or np.any(points[:,2]+delta>=origin[2]):raise ValueError('Dipoles must remain separated below the PMs')
    above=points.copy();below=points.copy();above[:,2]+=delta;below[:,2]-=delta
    force=np.zeros(3)
    for axis in range(3):
        for side in range(2):
            derivative=(rectangle_kernel(above,origin,size,axis,side)-rectangle_kernel(below,origin,size,axis,side))/(2*delta)
            force[axis]+=(2*side-1)*magnet['polarization_t'][2]/(4*math.pi)*float(np.sum(moment_weights*derivative))
    return force


def array_magnetization_force(magnets,points,moment_weights,delta=1e-7,workers=1):
    points=np.asarray(points,dtype=float);moments=np.asarray(moment_weights,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or moments.shape!=points.shape or not np.isfinite([points,moments]).all():
        raise ValueError('Invalid volume dipole sources')
    if workers>1:
        with ThreadPoolExecutor(max_workers=min(workers,len(magnets))) as pool:
            return np.asarray(list(pool.map(lambda magnet:magnetization_force(magnet,points,moments,delta),magnets)))
    return np.asarray([magnetization_force(m,points,moments,delta) for m in magnets])
