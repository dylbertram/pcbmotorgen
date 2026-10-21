"""Closed-air stress for an analytic source plus an affine reaction field.

Unlike cut_surface_force, total B is not affine, so triangle quadrature MUST
be refined independently. No source field, floor or source stress is subtracted.
"""
import numpy as np

from cut_surface_force import EDGES, MU0, clip_polygon


def triangles_on_face(vertices, fields, lower, upper, axis, side):
    plane=lower[axis] if side<0 else upper[axis]
    tangent=[i for i in range(3) if i!=axis];tolerance=1e-13
    lo=vertices.min(axis=1);hi=vertices.max(axis=1)
    selected=(lo[:,axis]<=plane+tolerance)&(hi[:,axis]>=plane-tolerance)
    selected&=(lo[:,axis]<plane-tolerance) if side>0 else (hi[:,axis]>plane+tolerance)
    for i in tangent:selected&=(lo[:,i]<upper[i])&(hi[:,i]>lower[i])
    triangles=[];vectors=[]
    for cell in np.flatnonzero(selected):
        v=vertices[cell];b=fields[cell];d=v[:,axis]-plane;points=[];values=[]
        for i in range(4):
            if abs(d[i])<=tolerance:
                p=v[i].copy();p[axis]=plane;points.append(p);values.append(b[i])
        for i,j in EDGES:
            if (d[i]<-tolerance and d[j]>tolerance) or (d[j]<-tolerance and d[i]>tolerance):
                f=d[i]/(d[i]-d[j]);points.append(v[i]+f*(v[j]-v[i]));values.append(b[i]+f*(b[j]-b[i]))
        if len(points)<3:continue
        points=np.asarray(points);values=np.asarray(values);centre=points.mean(axis=0)
        order=np.argsort(np.arctan2(points[:,tangent[1]]-centre[tangent[1]],points[:,tangent[0]]-centre[tangent[0]]))
        points=points[order];values=values[order]
        for i in tangent:
            points,values=clip_polygon(points,values,i,lower[i],True)
            points,values=clip_polygon(points,values,i,upper[i],False)
            if len(points)<3:break
        if len(points)<3:continue
        # Centroid fans commute with reflection. A first-vertex fan can choose
        # different diagonals on mirrored quadrilaterals and introduce spurious
        # transverse force when the analytical source makes stress nonquadratic.
        centre=points.mean(axis=0);centre_field=values.mean(axis=0)
        for i in range(len(points)):
            j=(i+1)%len(points)
            triangle=np.asarray([centre,points[i],points[j]])
            if np.linalg.norm(np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]))>0:
                triangles.append(triangle);vectors.append(np.asarray([centre_field,values[i],values[j]]))
    if not triangles:raise ValueError('Missing closed-air force face')
    return np.asarray(triangles),np.asarray(vectors)


def subdivide(values):
    a,b,c=values[:,0],values[:,1],values[:,2]
    ab=(a+b)/2;bc=(b+c)/2;ca=(c+a)/2
    return np.concatenate([np.stack(v,axis=1) for v in [(a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)]])


def box_force(vertices, reaction, lower, upper, source, depth):
    vertices=np.asarray(vertices,dtype=float);reaction=np.asarray(reaction,dtype=float)
    lower=np.asarray(lower,dtype=float);upper=np.asarray(upper,dtype=float)
    if vertices.ndim!=3 or vertices.shape[1:]!=(4,3) or reaction.shape!=vertices.shape or not np.isfinite([vertices,reaction]).all():
        raise ValueError('Expected finite affine reaction-field tetrahedra')
    if lower.shape!=(3,) or upper.shape!=(3,) or not np.isfinite([lower,upper]).all() or np.any(upper<=lower):
        raise ValueError('Invalid rectangular force surface')
    if type(depth) is not int or not 0<=depth<=6:raise ValueError('Choose triangle depth in [0,6]')
    faces={}
    for axis in range(3):
        for side in [-1,1]:
            points,values=triangles_on_face(vertices,reaction,lower,upper,axis,side)
            if len(points)*4**depth>3000000:raise ValueError('Quadrature memory cap exceeded; refine the air mesh instead')
            for _ in range(depth):points=subdivide(points);values=subdivide(values)
            area=np.linalg.norm(np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0]),axis=1)/2
            expected=float(np.prod(np.delete(upper-lower,axis)));coverage=abs(float(area.sum())/expected-1)
            if not np.isfinite(coverage) or coverage>1e-8:raise ValueError('Incomplete or duplicated force face')
            samples=(points.sum(axis=1)[:,None,:]+3*points)/6
            response=(values.sum(axis=1)[:,None,:]+3*values)/6
            incident=np.asarray(source(samples.reshape(-1,3)),dtype=float)
            if incident.shape!=(samples.size//3,3) or not np.isfinite(incident).all():raise ValueError('Invalid prescribed source field')
            total=response+incident.reshape(samples.shape)
            normal=np.zeros(3);normal[axis]=side
            traction=total*(total@normal)[:,:,None]-0.5*np.sum(total*total,axis=2)[:,:,None]*normal
            force=np.sum(area[:,None]*traction.mean(axis=1),axis=0)/MU0
            if not np.isfinite(force).all():raise ValueError('Nonfinite total-field stress')
            faces[f'{axis}/{side}']={'force_n':force.tolist(),'area_m2':float(area.sum()),
                'expected_area_m2':expected,'area_relative_error':coverage,'triangle_pieces':len(points)}
    return {'force_n':np.sum([v['force_n'] for v in faces.values()],axis=0).tolist(),'faces':faces,'triangle_depth':depth}
