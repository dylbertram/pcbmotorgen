"""Separate far-air element size from the physical exterior radius.

An explicit far-air control disables CAD curvature sizing. Otherwise the
stretched sphere's pole curvature silently imposes a radius-dependent second
size cap, even when the requested far-air maximum is held fixed.
"""
import math
import re


def with_far_mesh(geometry,size):
    if isinstance(size,bool) or not isinstance(size,(int,float)) or not math.isfinite(size) or size<=0:
        raise ValueError('Far-air mesh size must be positive and finite')
    result,count=re.subn(r'^Mesh\.MeshSizeMax=[^;]+;$',f'Mesh.MeshSizeMax={size:.17g};',geometry,flags=re.M)
    if count!=1:raise ValueError('Expected one global far-air mesh maximum')
    result,count=re.subn(r'^Mesh\.MeshSizeFromCurvature=[^;]+;$','Mesh.MeshSizeFromCurvature=0;',result,flags=re.M)
    if count!=1:raise ValueError('Expected one explicit CAD curvature sizing control')
    result,count=re.subn(r'^(Field\[\d+\]\.VOut=)[^;]+;$',lambda match:match.group(1)+f'{size:.17g};',result,flags=re.M)
    if count<1:raise ValueError('Expected explicit far-air background mesh fields')
    return result
