"""Outside-material field from explicitly integrated volume magnetization.

Exact free-space dipole Green kernel, no softened source radius or offset.
This reconstructs an exterior reaction field from a solved material state;
it is NOT valid inside a magnetized element, where local/self terms matter.
Direct A-curl field and source-quadrature/mesh controls remain separate evidence.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np

MU0=4e-7*np.pi


def dipole_field(points,sources,moments,workers=1):
    points=np.asarray(points,dtype=float);sources=np.asarray(sources,dtype=float);moments=np.asarray(moments,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or sources.ndim!=2 or sources.shape[1]!=3 or moments.shape!=sources.shape or not all(np.isfinite(x).all() for x in [points,sources,moments]):
        raise ValueError('Invalid exterior dipole-field arrays')
    if type(workers) is not int or workers<1:raise ValueError('Positive Green-kernel worker count required')
    def chunk(first):
        observations=points[first:first+128];result=np.zeros_like(observations)
        for begin in range(0,len(sources),4096):
            moment=moments[begin:begin+4096];r=observations[:,None,:]-sources[None,begin:begin+4096,:]
            squared=np.einsum('ijk,ijk->ij',r,r)
            if np.any(squared==0):raise ValueError('Singular dipole/self observation; no fitted radius is applied')
            inverse=np.power(squared,-1.5);projection=np.einsum('ijk,jk->ij',r,moment)
            result+=np.sum(3*(projection*inverse/squared)[:,:,None]*r-inverse[:,:,None]*moment[None,:,:],axis=1)
        return first,MU0/(4*np.pi)*result
    result=np.zeros_like(points);indices=range(0,len(points),128)
    if workers==1:
        for first,value in map(chunk,indices):result[first:first+len(value)]=value
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for first,value in pool.map(chunk,indices):result[first:first+len(value)]=value
    if not np.isfinite(result).all():raise ValueError('Nonfinite exterior reaction field')
    return result


def material_moments(work,degree):
    """Completed full-domain static initial state; no eddy-current contribution."""
    import json
    import ngsolve as ng
    from compare_reduced_fields import completed_receipt
    from post_project_force import sha
    from ngsolve_reduced import source_coefficient
    from vector_material import magnetization_b
    from volume_field_quadrature import sample
    report=json.loads((work/'summary.json').read_text());completed_receipt(report)
    if report['status'] not in ['completed-coupled-material-static-only','completed-nonlinear-ferrite-housing-motion-unqualified'] or report['failures'] or report['profile']['start_offset_m']!=0:
        raise ValueError('Need completed centred full-domain material bias')
    if ng.__version__!=report['version'] or sha(work/'mesh.vol')!=report['mesh_sha256'] or sha(work/'initial-reaction.sol')!=report['initial_solution_sha256']:
        raise ValueError('Material mesh, engine or equilibrium changed')
    mesh=ng.Mesh(str(work/'mesh.vol'));space=ng.HCurl(mesh,order=report['request']['order'],nograds=True,dirichlet='outer')
    state=ng.GridFunction(space);state.Load(str(work/'initial-reaction.sol'))
    source=source_coefficient(ng,report['model']).Compile();points=[];moments=[]
    for material in report['model']['stack']:
        if material['mu_r']<=1 or material['name']=='housing':continue
        moment=magnetization_b(ng,source+ng.curl(state),material['mu_r'],material['bsat_t']).Compile()
        p,m,w=sample(ng,mesh,moment,material['name'],degree);points.append(p);moments.append(m*w[:,None])
    if not points:raise ValueError('No material magnetization')
    return report,np.concatenate(points),np.concatenate(moments)


def exterior_points(model,points):
    points=np.asarray(points)
    for material in model['stack']:
        if material['mu_r']<=1:continue
        low=np.asarray(material['origin_m']);high=low+material['size_m']
        if np.any(np.all((points>=low)&(points<=high),axis=1)):
            raise ValueError('Exterior reaction reconstruction cannot evaluate inside/on magnetic material')
