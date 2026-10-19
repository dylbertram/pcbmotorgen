"""Closed-box Maxwell stress quadrature, air only, SI units.

The caller must sample every face outside all material and current sources.
This is not a force formula inside nonlinear material. Return paths matter for
induced-current fields, which must come from a separate valid field solution.
"""
import numpy as np

MU0 = 4e-7*np.pi


def box_faces(halfwidth, bottom, top, subdivisions, halfdepth=None):
    halfdepth=halfwidth if halfdepth is None else halfdepth
    if not (np.isfinite([halfwidth,halfdepth,bottom,top]).all() and halfwidth > 0 and halfdepth > 0 and top > bottom and subdivisions >= 2):
        raise ValueError('Invalid integration box')
    u = (np.arange(subdivisions)+0.5)/subdivisions
    a,b = np.meshgrid(u,u,indexing='ij')
    a,b = a.ravel(),b.ravel()
    faces = []
    for axis in range(3):
        other = [i for i in range(3) if i != axis]
        low = np.array([-halfwidth,-halfdepth,bottom])
        high = np.array([halfwidth,halfdepth,top])
        area = np.prod((high-low)[other])
        for side in [-1,1]:
            points = np.zeros((subdivisions**2,3))
            points[:,axis] = low[axis] if side == -1 else high[axis]
            for index, parameter in zip(other,[a,b]):
                points[:,index] = low[index]+parameter*(high[index]-low[index])
            normal = np.zeros(3)
            normal[axis] = side
            faces.append((points,normal,float(area/subdivisions**2)))
    return faces


def force(faces, fields):
    if len(faces) != 6 or len(fields) != 6:
        raise ValueError('All six faces are required')
    total = np.zeros(3)
    for (points,normal,weight), b in zip(faces,fields):
        b = np.asarray(b)
        if b.shape != points.shape or not np.isfinite(b).all():
            raise ValueError('Invalid surface field')
        traction = (b*(b@normal)[:,None]-0.5*(b*b).sum(axis=1)[:,None]*normal)/MU0
        total += traction.sum(axis=0)*weight
    return total
