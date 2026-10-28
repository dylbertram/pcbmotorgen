"""Cross-check a reduced-response report against archived physical inputs.

Hashes of output fields alone do not protect material/source metadata. Rebuild
the explicit model from the archived PMMOTOR, check source/material expressions
in the actual solved formulation, and check material bounds in physical mesh
coordinates before any postprocessor can label a numerical comparison passing.
"""
from pathlib import Path
import math

import numpy as np

from post_project_force import sha
from project_static import project
from reduced_potential import formulation, response_model


def same_model(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(same_model(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same_model(x,y) for x,y in zip(a,b))
    if type(a) in [int,float] and type(b) in [int,float]:return math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-16)
    return type(a) is type(b) and a==b


def validate_reduced_inputs(work,report):
    snapshots={}
    for group in ['source_snapshots','original_source_snapshots']:
        for path,entry in report.get(group,{}).items():
            archive=work/entry['snapshot']
            if sha(archive)!=entry['sha256']:raise ValueError('Changed archived source or input')
            if Path(path).suffix=='.pmmotor':snapshots[entry['sha256']]=archive
    model=report['model'];original=snapshots.get(model['source_sha256'])
    if original is None:raise ValueError('Missing archived project input')
    rebuilt=project(original,model['version_index'],[v/1e-3 for v in model['footprint_m']],model['array_centre_mm'])
    if not same_model(rebuilt,model):raise ValueError('Report model does not match the archived project and explicit pose')
    solver=response_model(model,report['quarter_symmetry'],report.get('omit_inert_regions',False))
    if solver!=report['solver_geometry_model']:raise ValueError('Changed response-material geometry')
    block=formulation(model,solver).split('Function {',1)[1].split('\n}\nConstraint',1)[0]
    for name in report['runs']:
        text=(work/name/'project.pro').read_text()
        if any(line.strip() and line.strip() not in text for line in block.splitlines()):
            raise ValueError('Solved source/material expressions do not match the recorded physical model')
    lines=(work/'project.msh').read_text().splitlines();start=lines.index('$Nodes');count=int(lines[start+1])
    nodes={int(v[0]):np.array(list(map(float,v[1:]))) for v in (row.split() for row in lines[start+2:start+2+count])}
    start=lines.index('$Elements');count=int(lines[start+1]);by_tag={m['tag']:set() for m in solver['stack']}
    for row in lines[start+2:start+2+count]:
        values=list(map(int,row.split()))
        if values[1]==4 and values[3] in by_tag:by_tag[values[3]].update(values[3+values[2]:])
    for material in solver['stack']:
        if not by_tag[material['tag']]:raise ValueError('Missing responding material')
        points=np.array([nodes[i] for i in by_tag[material['tag']]])
        low=np.asarray(material['origin_m']);high=low+material['size_m']
        if max(np.max(abs(points.min(axis=0)-low)),np.max(abs(points.max(axis=0)-high)))>1e-9:
            raise ValueError('Physical material bounds do not match the reported placement')
    return solver
