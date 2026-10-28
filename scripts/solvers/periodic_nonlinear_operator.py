"""Explicit gradient/full tangent of the existing periodic B-energy equations.

All coefficients are re-evaluated at every trial state. This avoids carrying
the prescribed source through second-order automatic differentiation, but does
not replace the nonlinear law with a frozen or scalar secant permeability.
Original automatic-energy trace audits remain an independent assembly check.
"""
from ngsolve_periodic_ac import tensor,MU0


class ExplicitNonlinearPlate:
    def __init__(self,ng,space,mesh,bx,bz,mu,bsat,conductivity,rule,rate=0.):
        self.state=ng.GridFunction(space);trial,test=space.TnT()
        measure=lambda name:ng.dx(definedon=mesh.Materials(name),intrules={ng.ET.TRIG:rule})
        xfield=bx+ng.grad(self.state)[1];zfield=bz+ng.grad(self.state)[0]
        squared=xfield*xfield+zfield*zfield;knee=bsat*mu/(mu-1);radius=ng.sqrt(ng.IfPos(squared,squared,1.))
        nu=ng.IfPos(squared-knee*knee,(1-bsat/radius)/MU0,1/(MU0*mu))
        gradient=ng.CoefficientFunction((nu*xfield-bx/MU0,nu*zfield-bz/MU0)).Compile()
        txx,txz,tzz=tensor(ng,xfield,zfield,mu,bsat)
        derivative=ng.CoefficientFunction((txx,txz,tzz)).Compile()
        self.residual=ng.LinearForm(space)
        self.residual+=(gradient[0]*ng.grad(test)[1]+gradient[1]*ng.grad(test)[0])*measure('plate')
        self.residual+=(ng.InnerProduct(ng.grad(self.state),ng.grad(test))/MU0)*measure('air|wall')
        self.matrix=ng.BilinearForm(space,symmetric=True)
        self.matrix+=(derivative[0]*ng.grad(trial)[1]*ng.grad(test)[1]+
            derivative[1]*(ng.grad(trial)[0]*ng.grad(test)[1]+ng.grad(trial)[1]*ng.grad(test)[0])+
            derivative[2]*ng.grad(trial)[0]*ng.grad(test)[0])*measure('plate')
        self.matrix+=(ng.InnerProduct(ng.grad(trial),ng.grad(test))/MU0)*measure('air|wall')
        if rate:
            self.residual+=(rate*conductivity*self.state*test)*measure('plate')
            self.residual+=(rate*25e6*self.state*test)*measure('wall')
            self.matrix+=(rate*conductivity*trial*test)*measure('plate')
            self.matrix+=(rate*25e6*trial*test)*measure('wall')

    def Apply(self,vector,result):
        self.state.vec.data=vector;self.residual.Assemble();result.data=self.residual.vec

    def AssembleLinearization(self,vector):
        self.state.vec.data=vector;self.matrix.Assemble()

    @property
    def mat(self):
        return self.matrix.mat
