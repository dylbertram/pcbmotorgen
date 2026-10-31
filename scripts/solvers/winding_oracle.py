"""Independent resistance, branch-current and 3D dL reconstruction.

The exported resistor-graph connectivity and arc tessellation still come from
Rust. This independently reconstructs physical R and force samples from its
geometric edges instead of reusing Rust current shares or sampled dL.
"""
import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def custom_stack(sim):
    stack = sim.get('pcb_stackup')
    if stack is None:return None
    copper, dielectric = stack['copper_m'], stack['dielectric_m']
    if len(copper)!=sim['num_layers'] or len(dielectric)!=sim['num_layers']-1:
        raise ValueError('PCB stackup layer count mismatch')
    values=np.asarray(copper+dielectric,dtype=float)
    if not np.isfinite(values).all() or np.any(values<=0) or not math.isclose(float(values.sum()),sim['pcb_thickness_m'],rel_tol=1e-9,abs_tol=1e-10):
        raise ValueError('Invalid PCB stackup thickness')
    return stack


def layer_z(sim,hints,layer):
    if isinstance(layer,bool) or not isinstance(layer,int) or not 0<=layer<sim['num_layers']:raise ValueError('Invalid copper layer')
    depths=hints.get('layer_z_m',[])
    stack=custom_stack(sim)
    z=depths[layer] if layer<len(depths) else (-sum(stack['copper_m'][:layer])-sum(stack['dielectric_m'][:layer])-stack['copper_m'][layer]/2 if stack else -layer*sim['pcb_thickness_m']/max(1,sim['num_layers']-1))
    if not np.isfinite(z):raise ValueError('Nonfinite layer depth')
    return float(z)


def edge_points(edge,sim,hints):
    geometry=edge['geometry']
    if geometry['kind']=='trace':
        xy=np.asarray(geometry['points_m'],dtype=float)
        if xy.ndim!=2 or xy.shape[1]!=2 or len(xy)<2:raise ValueError('Invalid trace polyline')
        points=np.column_stack([xy,np.full(len(xy),layer_z(sim,hints,geometry['layer']))])
    elif geometry['kind']=='via':
        if len(geometry['layers'])!=2:raise ValueError('Invalid barrel interval')
        xy=np.asarray(geometry['position_m'],dtype=float)
        if xy.shape!=(2,):raise ValueError('Invalid via position')
        points=np.column_stack([np.tile(xy,(2,1)),[layer_z(sim,hints,layer) for layer in geometry['layers']]])
    else:raise ValueError('Unknown conductor kind')
    if not np.isfinite(points).all():raise ValueError('Nonfinite conductor geometry')
    return points


def resistances(network,sim,drive,hints):
    rho=1.724e-8*(1+0.00393*(drive['winding_temp_c']-20))
    if not math.isfinite(rho) or rho<=0:raise ValueError('Invalid copper temperature')
    result=[]
    for edge in network['edges']:
        geometry=edge['geometry'];points=edge_points(edge,sim,hints)
        length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
        if geometry['kind']=='trace':
            layer=geometry['layer'];inner=sim['num_layers']>2 and layer not in [0,sim['num_layers']-1]
            oz=drive['inner_copper_oz'] if inner else drive['outer_copper_oz']
            stack=custom_stack(sim)
            area=sim['min_trace_m']*(stack['copper_m'][layer] if stack else oz*35e-6)
        else:area=math.pi*drive['via_plating_m']*(sim['min_via_drill_m']+drive['via_plating_m'])
        if not np.isfinite([length,area]).all() or min(length,area)<=0:raise ValueError('Invalid conductor dimensions')
        result.append(rho*length/area)
    return np.asarray(result)


def unit_currents(network,resistance):
    n=network['node_count'];edges=network['edges'];resistance=np.asarray(resistance,dtype=float)
    if resistance.shape!=(len(edges),) or not np.isfinite(resistance).all() or np.any(resistance<=0):raise ValueError('Invalid edge resistance')
    a=np.asarray([e['a'] for e in edges]);b=np.asarray([e['b'] for e in edges])
    if not len(edges) or min(a.min(),b.min())<0 or max(a.max(),b.max())>=n:raise ValueError('Invalid electrical nodes')
    terminal=np.asarray(network['terminal'],dtype=int);star=np.asarray(network['star'],dtype=int)
    if not len(terminal) or not len(star) or np.intersect1d(terminal,star).size:raise ValueError('Invalid terminal/return buses')
    if min(terminal.min(),star.min())<0 or max(terminal.max(),star.max())>=n:raise ValueError('Terminal outside network')
    g=1/resistance
    laplacian=coo_matrix((np.r_[g,g,-g,-g],(np.r_[a,b,a,b],np.r_[a,b,b,a])),shape=(n,n)).tocsr()
    potential=np.zeros(n);potential[terminal]=1.
    unknown=np.setdiff1d(np.arange(n),np.r_[terminal,star])
    potential[unknown]=spsolve(laplacian[unknown][:,unknown],-(laplacian@potential)[unknown])
    current=(potential[a]-potential[b])/resistance
    flow=np.bincount(a,weights=current,minlength=n)-np.bincount(b,weights=current,minlength=n)
    injected=float(flow[terminal].sum())
    if not np.isfinite(potential).all() or not math.isfinite(injected) or injected<=0:raise ValueError('Disconnected conductor network')
    shares=current/injected
    if np.max(abs(flow[unknown]),initial=0)>1e-9*injected or abs(flow[star].sum()/injected+1)>1e-9:
        raise ValueError('Independent conductor continuity failed')
    equivalent=1/injected
    if not np.isclose(float(np.sum(shares*shares*resistance)),equivalent,rtol=1e-9,atol=1e-12):raise ValueError('Independent conductor power balance failed')
    return shares,equivalent


def conductor_samples(network,shares,sim,hints,subdivisions):
    if isinstance(subdivisions,bool) or not isinstance(subdivisions,int) or not 1<=subdivisions<=4096:
        raise ValueError('Invalid conductor subdivision count')
    shares=np.asarray(shares,dtype=float)
    if shares.shape!=(len(network['edges']),) or not np.isfinite(shares).all():raise ValueError('Invalid current shares')
    positions=[];vectors=[]
    for edge,share in zip(network['edges'],shares):
        points=edge_points(edge,sim,hints)
        for a,b in zip(points[:-1],points[1:]):
            delta=b-a
            positions.extend(a+((np.arange(subdivisions)+0.5)/subdivisions)[:,None]*delta)
            vectors.extend(np.tile(delta*share/subdivisions,(subdivisions,1)))
    return np.asarray(positions),np.asarray(vectors)
