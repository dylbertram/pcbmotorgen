"""Closed-conductor DC basis with exactly compatible HDiv/L2 continuity.

Saved copper resistivity is an input, not a fitted circuit constant. A prescribed
nonconservative electric drive supplies the loop EMF. Exterior normal current
is zero; internal copper/drive interfaces stay open. This is DC only, not AC
skin/proximity or nonlinear magnetic coupling.
"""
import json

import numpy as np


class CurrentSolveFailure(ValueError):
    def __init__(self,message,details):
        super().__init__(message);self.details=details


def block_solve(matrix,rhs,free,flux_dofs,diagnostic=None,pressure_solver='factor'):
    """Bounded mixed solve: diagonal flux mass and pressure graph factor.

    Only the Schur preconditioner is approximate. MINRES solves/checks the
    original full mixed equations; this is not a resistor-graph replacement.
    """
    from scipy.sparse import coo_matrix,diags,triu
    from scipy.sparse.linalg import LinearOperator,minres,splu
    rows,columns,values=matrix.COO();size=len(free)
    sparse=coo_matrix((np.array(values),(np.array(rows),np.array(columns))),shape=(size,size)).tocsr()
    # NGSolve's Python COO lists can dominate memory. They are not needed by
    # MINRES or the pressure factor once the CSR copy owns its arrays.
    del rows,columns,values
    if triu(sparse,k=1).nnz==0:sparse=sparse+sparse.T-diags(sparse.diagonal())
    selected=np.flatnonzero(np.array(free,dtype=bool));operator=sparse[selected][:,selected].tocsr()
    del sparse
    split=int(np.count_nonzero(np.array(free,dtype=bool)[:flux_dofs]));diagonal=operator.diagonal()[:split]
    if np.any(diagonal<=0) or not np.isfinite(diagonal).all():raise ValueError('Nonpositive finite-current flux mass')
    inverse=1/diagonal;coupling=operator[split:,:split]
    schur=(coupling@diags(inverse)@coupling.T).tocsc()
    pressure_dofs=schur.shape[0];pressure_nonzeros=schur.nnz
    if pressure_solver=='factor':
        pressure=splu(schur,permc_spec='MMD_AT_PLUS_A',diag_pivot_thresh=0.)
        apply_pressure=pressure.solve;factor_nonzeros=int(pressure.nnz)
        pressure_metadata={'method':'exact sparse graph factor'}
    elif pressure_solver=='amg':
        import pyamg
        if pyamg.__version__!='5.3.0':raise ValueError('Pinned PyAMG5.3.0 required')
        pressure=pyamg.smoothed_aggregation_solver(schur.tocsr(),symmetry='symmetric',coarse_solver='pinv',max_coarse=64,
            presmoother=('gauss_seidel',{'sweep':'symmetric'}),postsmoother=('gauss_seidel',{'sweep':'symmetric'}))
        cycle=pressure.aspreconditioner(cycle='V');apply_pressure=lambda x:cycle@x;factor_nonzeros=None
        pressure_metadata={'method':'symmetric smoothed-aggregation V-cycle','version':pyamg.__version__,
            'level_dofs':[level.A.shape[0] for level in pressure.levels],
            'operator_complexity':float(pressure.operator_complexity()),
            'scope':'Linear preconditioner only; original full mixed residual and physical current/power gates unchanged'}
    else:raise ValueError('Unknown pressure preconditioner')
    del schur,coupling
    preconditioner=LinearOperator(operator.shape,matvec=lambda x:np.r_[inverse*x[:split],apply_pressure(x[split:])])
    iterations=[];right=np.array(rhs.FV().NumPy()[selected]);answer=np.zeros_like(right);passes=[]
    scale=max(float(np.linalg.norm(right)),1e-300)
    for refinement in range(4):
        defect=right-operator@answer;before=len(iterations)
        correction,info=minres(operator,defect,M=preconditioner,rtol=1e-13,maxiter=4000,callback=lambda x:iterations.append(1),check=True)
        answer+=correction;relative=float(np.linalg.norm(operator@answer-right))/scale
        passes.append({'pass':refinement,'minres_info':int(info),'iterations':len(iterations)-before,'original_relative_residual':relative})
        if diagnostic:diagnostic.write_text(json.dumps({'status':'running-mixed-linear-refinement','passes':passes},indent=2)+'\n')
        if info==0 and np.isfinite(relative) and relative<=1e-9:break
    else:
        raise CurrentSolveFailure('Mixed DC block solve failed its original-equation residual gate',{'passes':passes,'free_dofs':len(selected),'pressure_factor_dofs':pressure_dofs})
    result=rhs.CreateVector();result[:]=0.;result.FV().NumPy()[selected]=answer
    return result,{'method':'MINRES / flux diagonal plus pressure '+pressure_solver+' preconditioner','iterations':len(iterations),
        'relative_mixed_residual':relative,'free_dofs':len(selected),'pressure_factor_dofs':pressure_dofs,
        'matrix_nonzeros':operator.nnz,'pressure_nonzeros':pressure_nonzeros,'pressure_factor_nonzeros':factor_nonzeros,'pressure_preconditioner':pressure_metadata,
        'refinement_passes':passes,'scope':'Original mixed equations, no fitted current path or changed physical geometry'}


def exterior_flux_dofs(ng,mesh,space):
    for element in mesh.Elements():
        if element.type!=ng.ET.TET:raise ValueError('Closed-current boundary audit currently requires tetrahedra')
    result=[]
    for face in mesh.faces:
        adjacent=face.elements
        if any(element.VB()!=ng.VOL for element in adjacent):raise ValueError('Non-volume finite copper face adjacency')
        if len(adjacent)==1:result.extend(space.GetDofNrs(ng.NodeId(ng.FACE,face.nr)))
        elif len(adjacent)!=2:raise ValueError('Nonmanifold finite copper face')
    return sorted(set(d for d in result if d>=0))


def solve(ng,mesh,electric,resistivity,iterative=False,diagnostic=None,pressure_solver='factor'):
    if not np.isfinite(resistivity) or resistivity<=0:raise ValueError('Positive saved copper resistivity required')
    flux=ng.HDiv(mesh,order=0);potential=ng.L2(mesh,order=0);space=flux*potential
    j,p=space.TrialFunction();v,q=space.TestFunction();free=space.FreeDofs()
    exterior=exterior_flux_dofs(ng,mesh,flux)
    for dof in exterior:free[dof]=False
    free[flux.ndof]=False
    rules={ng.ET.TET:ng.IntegrationRule(ng.ET.TET,6)};dx=ng.dx(intrules=rules)
    matrix=ng.BilinearForm(space,symmetric=True)
    matrix+=(resistivity*ng.InnerProduct(j,v)+ng.div(v)*p+ng.div(j)*q)*dx
    load=ng.LinearForm(space);load+=ng.InnerProduct(electric,v)*dx
    matrix.Assemble();load.Assemble();solution=ng.GridFunction(space)
    solver_metadata={'method':'full mixed UMFPACK'}
    if iterative:solution.vec.data,solver_metadata=block_solve(matrix.mat,load.vec,free,flux.ndof,diagnostic,pressure_solver)
    else:solution.vec.data=matrix.mat.Inverse(free,inverse='umfpack')*load.vec
    residual=load.vec.CreateVector();residual.data=matrix.mat*solution.vec-load.vec;selected=np.array(free,dtype=bool)
    relative=float(np.linalg.norm(residual.FV().NumPy()[selected]))/max(float(np.linalg.norm(load.vec.FV().NumPy()[selected])),1e-300)
    current=solution.components[0]
    volume=float(ng.Integrate(ng.CoefficientFunction(1.),mesh,order=6))
    loss=float(ng.Integrate(resistivity*ng.InnerProduct(current,current),mesh,order=6))
    work=float(ng.Integrate(ng.InnerProduct(electric,current),mesh,order=6))
    divergence=float(ng.Integrate(ng.div(current)**2,mesh,order=6))
    net=np.asarray(ng.Integrate(current,mesh,order=6)).reshape(3)
    current_scale=np.sqrt(max(loss/resistivity*volume,1e-300));moment=float(np.linalg.norm(net))/current_scale
    gates={'relative_equation_residual':relative,'joule_power_w':loss,'source_power_w':work,
        'relative_power_balance':abs(work/loss-1) if loss>0 else None,'integrated_divergence_squared':divergence,
        'net_current_moment_a_m':net.tolist(),'net_current_relative_error':moment,'linear_solver':solver_metadata}
    if diagnostic:diagnostic.with_name('dc-gates.json').write_text(json.dumps(gates,indent=2,allow_nan=False)+'\n')
    if not np.isfinite([relative,loss,work,divergence,moment]).all() or relative>1e-9 or loss<=0 or abs(work/loss-1)>1e-8 or moment>1e-9:
        if diagnostic:solution.Save(str(diagnostic.with_name('unaccepted-current-potential.sol')))
        raise CurrentSolveFailure('Finite copper DC equation/continuity/power gate failed',gates)
    metadata={'flux_dofs':flux.ndof,'potential_dofs':potential.ndof,'dofs':space.ndof,'relative_equation_residual':relative,
        'joule_power_w':loss,'source_power_w':work,'relative_power_balance':abs(work/loss-1),'integrated_divergence_squared':divergence,
        'net_current_moment_a_m':net.tolist(),'net_current_relative_error':moment,'exterior_zero_flux_dofs':len(exterior),
        'source_model':'nonconservative imposed E; no fitted source radius; HDiv normal continuity and cellwise divergence constraint',
        'linear_solver':solver_metadata}
    return solution,metadata
