// Nonlinear 2D A_z formulation. B=mu0 H+clip(mu0*(Mu-1)*H, +/-Bsat).
// nu(B)=H/B; JacNL is the nonlinear part of the isotropic tangent tensor.
DefineConstant[Mu=130, Bsat=0.25, Biased=1, Thickness=0.0002, Relaxation=1];
Group {
  Air=Region[1]; Magnet=Region[2]; Plate=Region[3];
  Domain=Region[{1,2,3}]; Far=Region[10];
}
Function {
  mu0=4*Pi*1e-7;
  bk=Bsat*Mu/(Mu-1);
  nu[Region[{Air,Magnet}]]=1/mu0;
  nu[Plate]=!Biased ? 1/mu0 : ((Norm[$1]<=bk) ? 1/(mu0*Mu) : (1-Bsat/Norm[$1])/mu0);
  tangentNL[Plate]=(!Biased || Norm[$1]<=bk) ? TensorDiag[0,0,0] : Bsat/(mu0*Norm[$1]^3)*SquDyadicProduct[$1];
  br[Magnet]=Vector[0,1.34,0];
}
Constraint { { Name ZeroA; Case { { Region Far; Value 0; } } } }
Jacobian { { Name J; Case { { Region All; Jacobian Vol; } } } }
Integration { { Name I; Case { { Type Gauss; Case { { GeoElement Triangle; NumberOfPoints 6; } } } } } }
FunctionSpace {
  { Name Az; Type Form1P;
    BasisFunction { { Name sn; NameOfCoef an; Function BF_PerpendicularEdge; Support Domain; Entity NodesOf[All]; } }
    Constraint { { NameOfCoef an; EntityType NodesOf; NameOfConstraint ZeroA; } }
  }
}
Formulation {
  { Name PM; Type FemEquation;
    Quantity { { Name a; Type Local; NameOfSpace Az; } }
    Equation {
      Galerkin { [ nu[{d a}]*Dof{d a}, {d a} ]; In Domain; Jacobian J; Integration I; }
      Galerkin { JacNL [ tangentNL[{d a}]*Dof{d a}, {d a} ]; In Plate; Jacobian J; Integration I; }
      Galerkin { [ -nu[]*br[], {d a} ]; In Magnet; Jacobian J; Integration I; }
    }
  }
}
Resolution {
  { Name SolvePlate;
    System { { Name S; NameOfFormulation PM; } }
    Operation {
      InitSolution[S];
      If(Biased)
        IterativeLoop[200,1e-9,Relaxation] { GenerateJac[S]; SolveJac[S]; }
        Print[{$NLResidual,$NLIteration}, File "nonlinear.txt", Format "%.17g %.0f"];
        Test[$NLResidual>1e-9] { Error["Nonlinear plate solve failed to converge"]; }
      Else
        // With constant nu the first Newton system is the exact linear system.
        GenerateJac[S]; SolveJac[S];
        Print[{-1,1}, File "nonlinear.txt", Format "%.17g %.0f"];
      EndIf
      SaveSolution[S]; PostOperation[Samples];
    }
  }
}
PostProcessing {
  { Name Fields; NameOfFormulation PM;
    Quantity {
      { Name b; Value { Local { [ {d a} ]; In Domain; Jacobian J; } } }
      { Name potential; Value { Local { [ CompZ[{a}] ]; In Domain; Jacobian J; } } }
    }
  }
}
PostOperation {
  { Name Samples; NameOfPostProcessing Fields;
    Operation {
      // Avoid thousands of spatial searches through the strongly graded mesh.
      // Export the raw P1 potential, then integrate its element curl exactly.
      Print[potential, OnElementsOf Domain, Format Gmsh, File "potential.pos"];
    }
  }
}
