"""Reuse a sparse factor only as a preconditioner for the current full Jacobian.

No constitutive or tangent coefficient is frozen. Every returned Newton
direction is checked against the current matrix on free dofs. Failed CG falls
back to a fresh exact factor; failed linear checks reject the direction.
"""
import time

import numpy as np


class NewtonFactor:
    def __init__(self,ng,preconditioner=None):
        self.ng=ng;self.preconditioner=preconditioner
        self.stats={'solves':0,'factorizations':int(preconditioner is not None),'cg_iterations':0,'fallbacks':0,'maximum_relative_linear_residual':0.,'seconds':0.}

    def solve(self,matrix,rhs,freedofs):
        started=time.monotonic();free=np.array(freedofs,dtype=bool);scale=float(np.linalg.norm(rhs.FV().NumPy()[free]))
        result=rhs.CreateVector();result[:]=0.
        if scale==0:return result
        if self.preconditioner is None:
            self.preconditioner=matrix.Inverse(freedofs,inverse='sparsecholesky');self.stats['factorizations']+=1
        iterations=[]
        solver=self.ng.CGSolver(matrix,pre=self.preconditioner,tol=1e-12,maxiter=400,callback=lambda i,r:iterations.append(i),printrates=False)
        result.data=solver*rhs
        residual=rhs.CreateVector();residual.data=matrix*result-rhs
        relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/scale
        self.stats['cg_iterations']+=len(iterations)
        if not np.isfinite(relative) or relative>1e-9:
            self.preconditioner=matrix.Inverse(freedofs,inverse='sparsecholesky')
            self.stats['factorizations']+=1;self.stats['fallbacks']+=1;result.data=self.preconditioner*rhs
            residual.data=matrix*result-rhs;relative=float(np.linalg.norm(residual.FV().NumPy()[free]))/scale
        if not np.isfinite(relative) or relative>1e-9:raise ValueError('Current full Newton Jacobian linear solve failed')
        self.stats['solves']+=1;self.stats['maximum_relative_linear_residual']=max(self.stats['maximum_relative_linear_residual'],relative)
        self.stats['seconds']+=time.monotonic()-started
        return result
