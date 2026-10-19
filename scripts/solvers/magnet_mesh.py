"""Add local magnet-interface refinement without altering material geometry.

Size follows the existing meshing-coordinate convention: physical X/Y target,
with Z target divided by the explicit CAD Z stretch after mesh restoration.
The face bands refine both sides of an interface; the exterior target is held.
"""
import math
import re


def with_magnet_faces(geometry,model,size,stretch,far,physical_band=None):
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0 for v in [size,stretch,far]):
        raise ValueError('Positive finite interface mesh controls required')
    if size>far or not 1<=stretch<=8:raise ValueError('Invalid magnet interface size/stretch')
    if physical_band is not None and (isinstance(physical_band,bool) or not isinstance(physical_band,(int,float)) or not math.isfinite(physical_band) or physical_band<=0):
        raise ValueError('Physical interface band must be positive and finite')
    # Legacy default is size in meshing coordinates on every axis. An explicit
    # physical band keeps its Z reach after the CAD stretch is restored.
    margins=[size]*3 if physical_band is None else [physical_band,physical_band,physical_band*stretch]
    if not model.get('magnets'):raise ValueError('Missing magnet interfaces')
    backgrounds=re.findall(r'^Background Field=(\d+);$',geometry,re.M)
    minimum=re.findall(r'^Mesh\.MeshSizeMin=([^;]+);$',geometry,re.M)
    identifiers=[int(v) for v in re.findall(r'^Field\[(\d+)\]=',geometry,re.M)]
    if len(backgrounds)!=1 or len(minimum)!=1 or not identifiers:raise ValueError('Expected explicit background mesh and minimum')
    text=re.sub(r'^Mesh\.MeshSizeMin=[^;]+;$',f'Mesh.MeshSizeMin={min(float(minimum[0]),size):.17g};',geometry,flags=re.M)
    identifier=max(identifiers)+10;fields=[];lines=[]
    for magnet in model['magnets']:
        origin=list(magnet['origin_m']);dimensions=list(magnet['size_m'])
        if len(origin)!=3 or len(dimensions)!=3 or not all(math.isfinite(v) for v in origin+dimensions) or min(dimensions)<=0:
            raise ValueError('Invalid physical magnet bounds')
        origin[2]*=stretch;dimensions[2]*=stretch
        end=[a+b for a,b in zip(origin,dimensions)]
        for axis in range(3):
            for boundary in [origin[axis],end[axis]]:
                # A clipped mirror plane is not a magnet/air interface.
                if 'symmetry' in model and axis<2 and abs(boundary)<1e-14:continue
                low=[v-margin for v,margin in zip(origin,margins)];high=[v+margin for v,margin in zip(end,margins)]
                low[axis]=boundary-margins[axis];high[axis]=boundary+margins[axis]
                fields.append(identifier)
                lines.extend([f'Field[{identifier}]=Box;',f'Field[{identifier}].VIn={size:.17g};',f'Field[{identifier}].VOut={far:.17g};'])
                for i,name in enumerate('XYZ'):
                    lines.extend([f'Field[{identifier}].{name}Min={low[i]:.17g};',f'Field[{identifier}].{name}Max={high[i]:.17g};'])
                lines.append(f'Field[{identifier}].Thickness={2*size:.17g};');identifier+=1
    lines.extend([f'Field[{identifier}]=Min;',f'Field[{identifier}].FieldsList={{{backgrounds[0]},{",".join(map(str,fields))}}};',f'Background Field={identifier};'])
    return text+'\n'+'\n'.join(lines)+'\n'
