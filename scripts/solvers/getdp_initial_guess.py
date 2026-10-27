#!/usr/bin/env python3
"""Verify a P2 initial-guess transfer, not an independent physics solution.

GetDP's BF_Node_2E is lambda_i*lambda_j on tetrahedra, so its edge coefficient
is 4*(psi(midpoint)-(psi(i)+psi(j))/2). This is basis normalization, not fitting
a force or material constant. The installed GetDP reconstructs the transferred
gradient on ALL elements and is checked against the original NGSolve field.
No linear/nonlinear equation solve is performed by this transfer test.
"""
import argparse
import itertools
import json
import re
import shutil
from pathlib import Path

import numpy as np

from check_free_space import run
from ngsolve_reduced import load_solution
from post_project_force import sha
from post_reduced_force import case_field
from read_vtu import _vector_mesh
from reduced_inputs import validate_reduced_inputs
from reduced_potential import MU0
from source_snapshot import capture


def layout(mesh_path,pre_path):
    lines=mesh_path.read_text().splitlines();i=lines.index('$Nodes');n=int(lines[i+1])
    nodes={int(v[0]):np.array(list(map(float,v[1:]))) for v in (row.split() for row in lines[i+2:i+2+n])}
    i=lines.index('$Elements');n=int(lines[i+1]);elements={}
    for row in lines[i+2:i+2+n]:
        v=list(map(int,row.split()));elements[v[0]]=(v[1],v[3+v[2]:])
    # GetDP writes zero-based indices into its tag-sorted element array here,
    # not Gmsh element tags (GeoEntity.cpp::Geo_WriteToFile).
    ordered_elements=[elements[tag] for tag in sorted(elements)]
    lines=pre_path.read_text().splitlines();starts=[i for i,row in enumerate(lines) if row.startswith('$DofData')]
    if len(starts)!=1:raise ValueError('Need one scalar dof system')
    start=starts[0];total,free=map(int,lines[start+5].split());end=lines.index('$EndDofData',start)
    records=[row.split() for row in lines[start+6:end]]
    if len(records)!=total:raise ValueError('Unexpected scalar dof record count')
    i=lines.index('$ElementsXEdges');end=lines.index('$EndElementsXEdges',i);edge_nodes={}
    geometry_index,element_count=map(int,lines[i+1].split())
    if geometry_index!=0 or end-i-2!=element_count:raise ValueError('Unexpected element-edge map header')
    local_pairs={1:[(0,1)],2:[(0,1),(0,2),(1,2)],4:list(itertools.combinations(range(4),2))}
    explicit_edges={}
    for row in lines[i+2:end]:
        v=list(map(int,row.split()))
        if not 0<=v[0]<len(ordered_elements):raise ValueError('Invalid preprocessor element index')
        kind,vertices=ordered_elements[v[0]]
        if kind not in local_pairs or v[1]!=len(local_pairs[kind]):raise ValueError('Unsupported edge topology')
        # Use the documented GetDP edge topology, independently cross-checking
        # incidence. Neumann-boundary edges may have too few incident elements
        # to determine their two endpoints by set intersection alone.
        for edge,pair in zip(v[2:],local_pairs[kind]):
            edge=abs(edge)
            edge_nodes[edge]=edge_nodes.get(edge,set(vertices))&set(vertices)
            if len(edge_nodes[edge])<2:raise ValueError('Inconsistent global edge incidence')
            endpoints=tuple(sorted(vertices[j] for j in pair))
            if edge in explicit_edges and explicit_edges[edge]!=endpoints:raise ValueError('Inconsistent documented local edge topology')
            explicit_edges[edge]=endpoints
    parsed=[];seen=set()
    for row in records:
        basis,entity,harmonic,kind=map(int,row[:4])
        if basis not in [1,2] or harmonic!=0 or kind not in [1,2]:raise ValueError('Unsupported scalar basis/constraint')
        if kind==1:
            index=int(row[4])-1
            if not 0<=index<free or index in seen:raise ValueError('Invalid free scalar coefficient index')
            seen.add(index);parsed.append((basis,entity,index))
        elif any(float(v)!=0 for v in row[4:]):raise ValueError('Only zero exterior constraints are supported')
    if len(seen)!=free:raise ValueError('Missing free scalar coefficients')
    needed={entity for basis,entity,_ in parsed if basis==2}
    if any(entity not in explicit_edges or not set(explicit_edges[entity])<=edge_nodes[entity] for entity in needed):
        raise ValueError('Physical endpoints do not agree with global incidence')
    edges={entity:explicit_edges[entity] for entity in needed}
    return nodes,edges,parsed,free


def coefficients(nodes,edges,records,count,evaluate):
    node_values=dict.fromkeys(nodes,0.)
    needed={entity for basis,entity,_ in records if basis==1}
    edge_ids={entity for basis,entity,_ in records if basis==2}
    # Fixed boundary vertices are zero. Include endpoints of free interior
    # edges only if they are themselves free nodal unknowns.
    ids=sorted(needed)
    values=np.asarray(evaluate(np.array([nodes[i] for i in ids])),dtype=float).reshape(-1)
    if len(values)!=len(ids) or not np.isfinite(values).all():raise ValueError('Invalid nodal initial guess')
    node_values.update(zip(ids,values))
    ids=sorted(edge_ids);midpoints=np.array([(nodes[edges[i][0]]+nodes[edges[i][1]])/2 for i in ids])
    values=np.asarray(evaluate(midpoints),dtype=float).reshape(-1)
    if len(values)!=len(ids) or not np.isfinite(values).all():raise ValueError('Invalid edge initial guess')
    edge_values={i:4*(value-(node_values[edges[i][0]]+node_values[edges[i][1]])/2) for i,value in zip(ids,values)}
    result=np.zeros(count)
    for basis,entity,index in records:result[index]=node_values[entity] if basis==1 else edge_values[entity]
    return result


def transfer_formulation(text):
    operations='''Resolution {
  {Name SolvePM; System {{Name S; NameOfFormulation PM;}}
   Operation {InitSolution[S];CopySolution[InitialValues(),S];SaveSolution[S];PostOperation[TransferAudit];}}
}
'''
    text,n=re.subn(r'Resolution \{.*?(?=PostProcessing \{)',lambda _:operations,text,count=1,flags=re.S)
    if n!=1:raise ValueError('Unrecognized scalar resolution')
    return 'InitialValues()=ListFromFile["initial.txt"];\n'+text+'''
PostProcessing {
 {Name TransferFields;NameOfFormulation PM;
  Quantity {{Name gradient;Value {Local {[-mu0*{d phi}];In Domain;Jacobian J;}}}}}
}
PostOperation {
 {Name TransferAudit;NameOfPostProcessing TransferFields;
  Operation {Print[gradient,OnElementsOf Domain,Format Gmsh,File "initial-gradient.pos"];}}
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--ngsolve-work',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--getdp',type=Path,required=True)
    args=parser.parse_args();origin=args.source_work.resolve();independent=args.ngsolve_work.resolve();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous transfer checks')
    source=json.loads((origin/'summary.json').read_text());case_field(origin,source,'bare');validate_reduced_inputs(origin,source)
    ng,other,mesh,fes,solution=load_solution(independent)
    if other['order']!=2 or other['mesh_sha256']!=source['mesh_sha256'] or other['model']!=source['model']:
        raise ValueError('Initial guess must use the identical physical mesh, model and P2 space')
    nodes,edges,records,count=layout(origin/'project.msh',origin/'bare/project.pre')
    if count!=np.count_nonzero(np.array(fes.FreeDofs(),dtype=bool)):raise ValueError('Independent scalar spaces have different free dimensions')
    def evaluate(points):return np.asarray(solution(mesh(points[:,0],points[:,1],points[:,2])),dtype=float)
    values=coefficients(nodes,edges,records,count,evaluate)
    work.mkdir(parents=True);shutil.copy2(origin/'project.msh',work/'project.msh')
    np.savetxt(work/'initial.txt',values,fmt='%.17g')
    text=transfer_formulation((origin/'bare/project.pro').read_text());(work/'project.pro').write_text(text)
    report={'status':'running','scope':__doc__,'method':'NGSolve-to-GetDP-H1-P2-initial-guess-only',
        'mesh_sha256':source['mesh_sha256'],'source_summary_sha256':sha(origin/'summary.json'),
        'independent_summary_sha256':sha(independent/'summary.json'),'initial_values_sha256':sha(work/'initial.txt'),
        'coefficient_count':count,'getdp_executable_sha256':sha(args.getdp.resolve()),'failures':[]}
    report['source_snapshots']=capture(work,[Path(__file__),*[Path(__file__).parent/name for name in ['ngsolve_reduced.py','read_vtu.py','reduced_inputs.py']]])
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-solve','SolvePM','-setnumber','Mode','2','-v','4'],work,'transfer.log')
        if sha(work/'project.pre')!=sha(origin/'bare/project.pre'):raise ValueError('Transferred scalar dof ordering changed')
        field=work/'initial-gradient.pos';stat=field.stat()
        vertices,vectors,*_=_vector_mesh(str(field),stat.st_mtime_ns,stat.st_size,'gradient')
        centres=vertices.mean(axis=1)
        expected=np.asarray(ng.grad(solution)(mesh(centres[:,0],centres[:,1],centres[:,2])),dtype=float).reshape(-1,3)*(-MU0)
        actual=vectors.mean(axis=1);absolute=float(np.max(abs(actual-expected)))
        relative=float(np.linalg.norm(actual-expected)/np.linalg.norm(expected))
        report.update(maximum_gradient_error_t=absolute,relative_gradient_l2_error=relative,checked_elements=len(vertices))
        if absolute>1e-10 or relative>1e-9:raise ValueError('Transferred physical gradient differs from the independent field')
        for path,entry in report['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Transfer implementation changed')
        report['status']='verified-initial-guess-transfer-only';save();print(json.dumps({k:report[k] for k in ['coefficient_count','maximum_gradient_error_t','relative_gradient_l2_error','checked_elements']}))
    except BaseException as error:
        report.update(status='failed',failures=[str(error)]);save();raise


if __name__=='__main__':main()
