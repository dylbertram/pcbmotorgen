"""Generate an anisotropic mesh in stretched CAD coordinates, then undo it.

The PDE, PM polarization, materials, force surfaces and oracle stay in physical
SI coordinates. This is a mesh construction technique, not physical Z scaling
or a permeability correction. Physical mesh validation remains mandatory.
"""
import copy
import math
import re
from pathlib import Path


def stretched_geometry(model,mesh,gap_mesh,radius,stretch,quarter=False):
    from project_static import geometry
    from project_symmetry import quarter_geometry
    if not math.isfinite(stretch) or not 1<=stretch<=8:raise ValueError('Mesh stretch must be between one and eight')
    if stretch*gap_mesh>mesh:raise ValueError('Stretched vertical target exceeds the in-plane mesh target')
    scaled=copy.deepcopy(model)
    for group in ['magnets','stack']:
        scaled[group]=[]
        for original in model[group]:
            obj=copy.deepcopy(original)
            obj['origin_m']=[*original['origin_m'][:2],original['origin_m'][2]*stretch]
            obj['size_m']=[*original['size_m'][:2],original['size_m'][2]*stretch]
            scaled[group].append(obj)
    text=(quarter_geometry if quarter else geometry)(scaled,mesh,gap_mesh*stretch,radius)
    if stretch==1:return text
    sphere=f'Sphere(1)={{0,0,0,{radius:.17g}}};'
    if text.count(sphere)!=1:raise ValueError('Unexpected sphere construction')
    text=text.replace(sphere,sphere+f'\nDilate {{{{0,0,0}},{{1,1,{stretch:.17g}}}}} {{Volume{{1}};}}')
    if quarter:
        box=f'Box(990001)={{0,0,{-radius:.17g},{radius:.17g},{radius:.17g},{2*radius:.17g}}};'
        if text.count(box)!=1:raise ValueError('Unexpected quarter clipping box')
        text=text.replace(box,f'Box(990001)={{0,0,{-radius*stretch:.17g},{radius:.17g},{radius:.17g},{2*radius*stretch:.17g}}};')
        count=0
        def plane(match):
            nonlocal count
            values=[float(v) for v in match.group(2).split(',')]
            if len(values)!=6:raise ValueError('Unexpected symmetry selector')
            # OCC's dilated B-spline face can carry a larger bounding-box
            # tolerance than the original analytic sphere. Expand only the
            # entity query; physical plane nodes are still checked at 1e-10 m.
            epsilon=max(radius*1e-8,1e-6);padding=2*stretch*epsilon
            for axis in range(3):
                values[axis]-=padding;values[axis+3]+=padding
            values[2]*=stretch;values[5]*=stretch;count+=1
            return match.group(1)+','.join(f'{v:.17g}' for v in values)+match.group(3)
        text=re.sub(r'^(sym[xy]\[\]=Surface In BoundingBox \{)([^}]+)(\};)$',plane,text,flags=re.M)
        if count!=2:raise ValueError('Missing stretched symmetry selectors')
    return text


def physical_mesh(source,destination,stretch,radius=None):
    if not math.isfinite(stretch) or not 1<=stretch<=8:raise ValueError('Invalid inverse mesh stretch')
    source=Path(source);destination=Path(destination)
    if destination.exists():raise ValueError('Preserve the existing physical mesh')
    lines=source.read_text().splitlines()
    start=lines.index('$MeshFormat')
    if lines[start+1].split()[:2]!=['2.2','0']:raise ValueError('Expected an ASCII MSH2 mesh')
    start=lines.index('$Nodes');count=int(lines[start+1])
    if count<=0 or lines[start+2+count]!='$EndNodes':raise ValueError('Invalid mesh node section')
    outer=set()
    if radius is not None:
        if not math.isfinite(radius) or radius<=0:raise ValueError('Invalid physical air radius')
        elements=lines.index('$Elements');element_count=int(lines[elements+1])
        for row in lines[elements+2:elements+2+element_count]:
            values=list(map(int,row.split()))
            if values[1]==2 and values[2]>=1 and values[3]==1001:outer.update(values[3+values[2]:])
        if not outer:raise ValueError('Missing exterior surface for sphere reprojection')
    for index in range(start+2,start+2+count):
        values=lines[index].split()
        if len(values)!=4:raise ValueError('Invalid mesh node')
        coordinates=list(map(float,values[1:]))
        if not all(math.isfinite(v) for v in coordinates):raise ValueError('Nonfinite meshing coordinate')
        coordinates[2]/=stretch
        if int(values[0]) in outer:
            norm=math.sqrt(sum(v*v for v in coordinates))
            # Restore the exact original sphere after OCC's approximate
            # ellipsoid dilation. Never project an interface or plane onto it.
            if norm==0 or abs(norm-radius)>1e-7:raise ValueError('Exterior is not within CAD tolerance of the physical sphere')
            coordinates=[v*radius/norm for v in coordinates]
        lines[index]=values[0]+' '+' '.join(f'{v:.17g}' for v in coordinates)
    with destination.open('x') as output:output.write('\n'.join(lines)+'\n')
