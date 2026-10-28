"""Integrate quadratic Maxwell stress on planar cuts of affine tetra fields.

This removes surface quadrature error for the archived piecewise-linear B,
not the underlying FEM discretization error. Coverage is checked independently
on all six full rectangular faces. No nodal smoothing or force scaling is used.
"""
import itertools

import numpy as np

MU0=4e-7*np.pi
EDGES=list(itertools.combinations(range(4),2))


def reflected_tetrahedra(vertices,fields):
    """Reconstruct full signed B and physical coordinates from x/y symmetry."""
    if np.any(vertices[:,:,:2]<-1e-10):raise ValueError('Expected a positive-x/y quarter field')
    signs=[np.array([x,y,1.]) for x,y in itertools.product([1.,-1.],repeat=2)]
    return np.concatenate([vertices*s for s in signs]),np.concatenate([fields*s for s in signs])


def clip_polygon(points,fields,axis,bound,keep_greater):
    if not len(points):return points,fields
    output=[];values=[]
    previous=points[-1];previous_field=fields[-1]
    old=(previous[axis]>=bound) if keep_greater else (previous[axis]<=bound)
    for point,value in zip(points,fields):
        inside=(point[axis]>=bound) if keep_greater else (point[axis]<=bound)
        if inside!=old:
            fraction=(bound-previous[axis])/(point[axis]-previous[axis])
            output.append(previous+fraction*(point-previous));values.append(previous_field+fraction*(value-previous_field))
        if inside:output.append(point);values.append(value)
        previous=point;previous_field=value;old=inside
    return np.asarray(output),np.asarray(values)


def face_force(vertices,fields,lower,upper,axis,side):
    plane=lower[axis] if side<0 else upper[axis]
    normal=np.zeros(3);normal[axis]=side
    tangential=[i for i in range(3) if i!=axis]
    lo=vertices.min(axis=1);hi=vertices.max(axis=1)
    # A half-open convention uses the tetra on the box-interior side if an
    # entire tetra face lies on the cut, avoiding a duplicated positive area.
    tolerance=1e-13
    selected=(lo[:,axis]<=plane+tolerance)&(hi[:,axis]>=plane-tolerance)
    selected&=(lo[:,axis]<plane-tolerance) if side>0 else (hi[:,axis]>plane+tolerance)
    for i in tangential:selected&=(lo[:,i]<upper[i])&(hi[:,i]>lower[i])
    total=np.zeros(3);area=0.;pieces=0
    for cell in np.flatnonzero(selected):
        v=vertices[cell];b=fields[cell];distance=v[:,axis]-plane
        points=[];values=[]
        for i in range(4):
            if abs(distance[i])<=tolerance:
                point=v[i].copy();point[axis]=plane;points.append(point);values.append(b[i])
        for i,j in EDGES:
            if (distance[i]<-tolerance and distance[j]>tolerance) or (distance[j]<-tolerance and distance[i]>tolerance):
                fraction=distance[i]/(distance[i]-distance[j])
                points.append(v[i]+fraction*(v[j]-v[i]));values.append(b[i]+fraction*(b[j]-b[i]))
        if len(points)<3:continue
        points=np.asarray(points);values=np.asarray(values)
        centre=points.mean(axis=0)
        order=np.argsort(np.arctan2(points[:,tangential[1]]-centre[tangential[1]],points[:,tangential[0]]-centre[tangential[0]]))
        points=points[order];values=values[order]
        for i in tangential:
            points,values=clip_polygon(points,values,i,lower[i],True)
            points,values=clip_polygon(points,values,i,upper[i],False)
            if len(points)<3:break
        if len(points)<3:continue
        for i in range(1,len(points)-1):
            triangle=points[[0,i,i+1]];vectors=values[[0,i,i+1]]
            weight=float(np.linalg.norm(np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0])))/2
            if weight==0:continue
            # Symmetric degree-two triangle rule. B is affine on this cell,
            # hence each component of its Maxwell stress is exactly quadratic.
            samples=(vectors.sum(axis=0)[None,:]+3*vectors)/6
            stress=samples*(samples@normal)[:,None]-0.5*np.sum(samples*samples,axis=1)[:,None]*normal
            total+=weight*np.mean(stress,axis=0)/MU0;area+=weight;pieces+=1
    expected=float(np.prod((upper-lower)[tangential]))
    error=abs(area/expected-1)
    if not np.isfinite(total).all() or not np.isfinite(error) or error>1e-8:
        raise ValueError(f'Incomplete or duplicated force face axis={axis} side={side}: area {area}, expected {expected}')
    return {'force_n':total.tolist(),'area_m2':area,'expected_area_m2':expected,
            'area_relative_error':error,'triangle_pieces':pieces}


def box_force(vertices,fields,lower,upper):
    vertices=np.asarray(vertices,dtype=float);fields=np.asarray(fields,dtype=float)
    lower=np.asarray(lower,dtype=float);upper=np.asarray(upper,dtype=float)
    if vertices.ndim!=3 or vertices.shape[1:]!=(4,3) or fields.shape!=vertices.shape or not np.isfinite(vertices).all() or not np.isfinite(fields).all():
        raise ValueError('Expected finite tetra vertices and affine field vectors')
    if lower.shape!=(3,) or upper.shape!=(3,) or not np.isfinite([lower,upper]).all() or np.any(upper<=lower):
        raise ValueError('Expected finite positive rectangular box dimensions')
    faces={f'{axis}/{side}':face_force(vertices,fields,lower,upper,axis,side) for axis in range(3) for side in [-1,1]}
    total=np.sum([face['force_n'] for face in faces.values()],axis=0)
    return {'force_n':total.tolist(),'faces':faces}
