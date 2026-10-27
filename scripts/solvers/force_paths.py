"""Closed stress surfaces chosen from physical bounds, never solved fields.

The remote family splits the open stator/mover gap at fixed fractions. Its
other faces expand by 1/2/3 mm, avoiding the ideal sharp magnet corners. Both
families remain distinct audits; a remote pass cannot relabel a near failure.
"""
import numpy as np

from post_project_balance import bounds


def force_paths(model,name,remote=False):
    if name not in ['stator','mover']:raise ValueError('Unknown force body')
    lower,upper=bounds(model['stack'] if name=='stator' else model['magnets'])
    gap_lower=bounds(model['stack'])[1][2];gap_upper=bounds(model['magnets'])[0][2]
    if not np.isfinite([lower,upper,gap_lower*np.ones(3),gap_upper*np.ones(3)]).all() or gap_upper<=gap_lower:
        raise ValueError('Need finite separate stator/mover bounds')
    paths={}
    for i,c in enumerate([0.0001,0.0002,0.0003]):
        if not remote:
            if c>=gap_upper-gap_lower:raise ValueError('Force surfaces would intersect the other body')
            low=lower-c;high=upper+c;key=str(c)
        else:
            expansion=[0.001,0.002,0.003][i]
            plane=gap_lower+[0.35,0.5,0.65][i]*(gap_upper-gap_lower)
            low=lower-expansion;high=upper+expansion
            if name=='mover':low[2]=plane
            else:high[2]=plane
            key=str(i)
        paths[key]=(low,high)
    return paths
