"""Exact x/y mirror reduction for centred isotropic axial-PM static jobs.

The potential is even on both symmetry planes; only the spherical exterior is
Dirichlet. Full-domain fields are reconstructed for unchanged full closed-air
force surfaces. No inferred force multiplier or field/force gate relaxation.
"""
import copy

import numpy as np


def quarter_model(model):
    reduced=copy.deepcopy(model)
    for group in ['magnets','stack']:
        objects=model[group]
        for obj in objects:
            if group=='magnets' and not np.allclose(obj['polarization_t'][:2],0,rtol=0,atol=1e-15):
                raise ValueError('Quarter reduction requires axial magnet polarization')
            origin=np.asarray(obj['origin_m']);size=np.asarray(obj['size_m'])
            for axis in [0,1]:
                mirrored=origin.copy();mirrored[axis]=-origin[axis]-size[axis]
                matches=[]
                for other in objects:
                    if not np.allclose(other['origin_m'],mirrored,rtol=0,atol=1e-12) or not np.allclose(other['size_m'],size,rtol=0,atol=1e-12):continue
                    if any(other.get(key)!=obj.get(key) for key in ['material','mu_r','bsat_t','polarization_t']):continue
                    matches.append(other)
                if len(matches)!=1:raise ValueError('Geometry/materials are not exactly mirror symmetric about x=0 and y=0')
        clipped=[]
        for obj in objects:
            origin=np.asarray(obj['origin_m'],dtype=float);end=origin+obj['size_m']
            origin[:2]=np.maximum(origin[:2],0.)
            if np.any(end<=origin):continue
            clone=copy.deepcopy(obj);clone['origin_m']=origin.tolist();clone['size_m']=(end-origin).tolist()
            clipped.append(clone)
        reduced[group]=clipped
        before=sum(float(np.prod(o['size_m'])) for o in objects)
        after=sum(float(np.prod(o['size_m'])) for o in clipped)
        if objects and not np.isclose(after*4,before,rtol=1e-12,atol=0):raise ValueError('Quarter-volume conservation failed')
    reduced['symmetry']={'planes':['x=0','y=0'],'scalar_potential_parity':['even','even'],
                         'field_reconstruction':'Bx odd in x, By odd in y, Bz even in x/y; evaluate original full force surfaces'}
    return reduced


def quarter_geometry(model,mesh,gap_mesh,radius):
    from project_static import geometry
    if 'symmetry' not in model:raise ValueError('A validated quarter model is required')
    text=geometry(model,mesh,gap_mesh,radius)
    sphere=f'Sphere(1)={{0,0,0,{radius:.17g}}};'
    cut=(sphere+f'\nBox(990001)={{0,0,{-radius:.17g},{radius:.17g},{radius:.17g},{2*radius:.17g}}};\n'
         'quarter[]=BooleanIntersection{Volume{1};Delete;}{Volume{990001};Delete;};')
    if text.count(sphere)!=1:raise ValueError('Unexpected base sphere geometry')
    text=text.replace(sphere,cut)
    original='air[]=BooleanDifference{Volume{1};Delete;}'
    if text.count(original)!=1:raise ValueError('Unexpected base air subtraction')
    text=text.replace(original,'air[]=BooleanDifference{Volume{quarter[]};Delete;}')
    outer='Physical Surface("outer",1001)={outer[]};'
    if text.count(outer)!=1:raise ValueError('Unexpected base exterior boundary')
    # OCC bounding boxes include CAD-kernel tolerances around a plane. Select
    # with a micron envelope, then validate actual mesh nodes to 0.1 nm below.
    epsilon=max(radius*1e-8,1e-6)
    planes=(f'symx[]=Surface In BoundingBox {{{-epsilon:.17g},{-radius-epsilon:.17g},{-radius-epsilon:.17g},{epsilon:.17g},{radius+epsilon:.17g},{radius+epsilon:.17g}}};\n'
            f'symy[]=Surface In BoundingBox {{{-radius-epsilon:.17g},{-epsilon:.17g},{-radius-epsilon:.17g},{radius+epsilon:.17g},{epsilon:.17g},{radius+epsilon:.17g}}};\n'
            'For i In {0:#symx[]-1}\n  outer[]-={symx[i],-symx[i]};\nEndFor\n'
            'For i In {0:#symy[]-1}\n  outer[]-={symy[i],-symy[i]};\nEndFor\n'
            'Physical Surface("symmetry_x",1002)={symx[]};\nPhysical Surface("symmetry_y",1003)={symy[]};\n'+outer)
    return text.replace(outer,planes)


def mirrored_sample(path,points,name='magnetic flux density e',reader=None):
    if reader is None:
        from read_vtu import sample_vector
        reader=sample_vector
    points=np.asarray(points,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Invalid mirrored observations')
    folded=points.copy();folded[:,:2]=abs(folded[:,:2])
    fields=np.asarray(reader(path,folded,name),dtype=float).copy()
    if fields.shape!=points.shape or not np.isfinite(fields).all():raise ValueError('Invalid quarter field')
    fields[:,:2]*=np.sign(points[:,:2])
    return fields


def validate_quarter_mesh(path):
    lines=path.read_text().splitlines();start=lines.index('$Nodes');count=int(lines[start+1])
    nodes={int(v[0]):np.asarray(list(map(float,v[1:]))) for v in (row.split() for row in lines[start+2:start+2+count])}
    if any(np.any(v[:2]<-1e-10) for v in nodes.values()):raise ValueError('Quarter mesh extends outside the symmetry domain')
    start=lines.index('$Elements');count=int(lines[start+1]);surfaces={1002:set(),1003:set()}
    for row in lines[start+2:start+2+count]:
        values=list(map(int,row.split()))
        if values[1]==2 and values[3] in surfaces:surfaces[values[3]].update(values[3+values[2]:])
    for axis,tag in enumerate([1002,1003]):
        if not surfaces[tag] or any(abs(nodes[node][axis])>1e-10 for node in surfaces[tag]):
            raise ValueError('Missing or incorrect natural symmetry plane')
    return {'symmetry_x_nodes':len(surfaces[1002]),'symmetry_y_nodes':len(surfaces[1003])}
