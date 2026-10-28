"""Refine the air where finite mover stresses and winding fields are observed.

Reduced-potential meshes have no PM material interfaces. Removing those CAD
volumes must not also remove air resolution around the physical PMs. This box
is a numerical field-resolution control, not a fictitious magnetic material.
Band reach is in physical metres; CAD Z is stretched only for mesh generation.
"""
import math
import re


def with_observation_band(geometry,model,size,band,stretch,far):
    if any(type(v) not in [int,float] or not math.isfinite(v) or v<=0 for v in [size,band,stretch,far]):
        raise ValueError('Finite positive observation-band controls required')
    if not 1<=stretch<=8 or size>far:raise ValueError('Invalid observation size/stretch')
    if not model.get('magnets'):raise ValueError('Need actual source/mover bounds')
    background=re.findall(r'^Background Field=(\d+);$',geometry,re.M)
    identifiers=[int(v) for v in re.findall(r'^Field\[(\d+)\]=',geometry,re.M)]
    if len(background)!=1 or not identifiers:raise ValueError('Missing explicit geometry sizing fields')
    low=[min(m['origin_m'][axis] for m in model['magnets'])-band for axis in range(3)]
    high=[max(m['origin_m'][axis]+m['size_m'][axis] for m in model['magnets'])+band for axis in range(3)]
    low[2]*=stretch;high[2]*=stretch
    field=max(identifiers)+10
    lines=[f'Field[{field}]=Box;',f'Field[{field}].VIn={size:.17g};',f'Field[{field}].VOut={far:.17g};']
    for axis,name in enumerate('XYZ'):
        lines.extend([f'Field[{field}].{name}Min={low[axis]:.17g};',f'Field[{field}].{name}Max={high[axis]:.17g};'])
    lines.extend([f'Field[{field}].Thickness={2*size:.17g};',f'Field[{field+1}]=Min;',
                  f'Field[{field+1}].FieldsList={{{background[0]},{field}}};',f'Background Field={field+1};'])
    return geometry+'\n'+'\n'.join(lines)+'\n'
