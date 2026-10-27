// Scalar-potential magnetostatics: B = -mu0 grad(phi) + Br in the magnet.
// Only a free-space installation/formulation check. Not a nonlinear solver.
Group {
  Air = Region[1]; Magnet = Region[2]; Domain = Region[{1,2}]; Outer = Region[3];
}
Function {
  mu0 = 4*Pi*1e-7;
  br[Air] = Vector[0,0,0]; br[Magnet] = Vector[0,0,1.34];
}
Constraint {
  { Name Boundary; Case { { Region Outer; Value 0; } } }
}
Jacobian { { Name J; Case { { Region All; Jacobian Vol; } } } }
Integration {
  { Name I; Case { { Type Gauss; Case { { GeoElement Tetrahedron; NumberOfPoints 4; } } } } }
}
FunctionSpace {
  { Name H1; Type Form0;
    BasisFunction {
      { Name sn; NameOfCoef pn; Function BF_Node; Support Domain; Entity NodesOf[All]; }
      { Name se; NameOfCoef pe; Function BF_Node_2E; Support Domain; Entity EdgesOf[All]; }
    }
    Constraint {
      { NameOfCoef pn; EntityType NodesOf; NameOfConstraint Boundary; }
      { NameOfCoef pe; EntityType EdgesOf; NameOfConstraint Boundary; }
    }
  }
}
Formulation {
  { Name PM; Type FemEquation;
    Quantity { { Name phi; Type Local; NameOfSpace H1; } }
    Equation {
      Galerkin { [ mu0 * Dof{d phi}, {d phi} ]; In Domain; Jacobian J; Integration I; }
      Galerkin { [ -br[], {d phi} ]; In Magnet; Jacobian J; Integration I; }
    }
  }
}
Resolution {
  { Name SolvePM;
    System { { Name S; NameOfFormulation PM; } }
    Operation { Generate[S]; Solve[S]; SaveSolution[S]; PostOperation[Samples]; }
  }
}
PostProcessing {
  { Name Fields; NameOfFormulation PM;
    Quantity { { Name b; Value { Local { [ -mu0 * {d phi} + br[] ]; In Domain; Jacobian J; } } } }
  }
}
PostOperation {
  { Name Samples; NameOfPostProcessing Fields;
    Operation {
      Print[b, OnLine {{-0.003, 0, 0} {0.003, 0, 0}} {24}, Format SimpleTable, File "field.txt"];
    }
  }
}
