// Current-free 3D nonlinear scalar potential. No conducting-current physics.
// H=-grad(phi); B=mu0*H+J(H)+Br. J has a two-slope saturation law.
DefineConstant[Mu=130,Bsat=0.25,Mode=2,Relaxation=1]; // 0 bare, 1 linear, 2 nonlinear
Group {
  Air=Region[1]; Magnet=Region[2]; Plate=Region[3];
  Domain=Region[{1,2,3}]; Outer=Region[4];
}
Function {
  mu0=4*Pi*1e-7;
  hk=Bsat/(mu0*(Mu-1));
  br[Region[{Air,Plate}]]=Vector[0,0,0]; br[Magnet]=Vector[0,0,1.34];
  permeability[Region[{Air,Magnet}]]=mu0;
  permeability[Plate]=(Mode==0) ? mu0 : ((Mode==1 || Norm[$1]<=hk) ? mu0*Mu : mu0+Bsat/Norm[$1]);
  tangentNL[Plate]=(Mode!=2 || Norm[$1]<=hk) ? TensorDiag[0,0,0] : -Bsat/Norm[$1]^3*SquDyadicProduct[$1];
}
Constraint {{ Name Boundary; Case {{ Region Outer; Value 0; }} }}
Jacobian {{ Name J; Case {{ Region All; Jacobian Vol; }} }}
Integration {{ Name I; Case {{ Type Gauss; Case {{ GeoElement Tetrahedron; NumberOfPoints 15; }} }} }}
FunctionSpace {
  { Name H1; Type Form0;
    BasisFunction {
      {Name sn; NameOfCoef pn; Function BF_Node; Support Domain; Entity NodesOf[All];}
      {Name se; NameOfCoef pe; Function BF_Node_2E; Support Domain; Entity EdgesOf[All];}
    }
    Constraint {
      {NameOfCoef pn; EntityType NodesOf; NameOfConstraint Boundary;}
      {NameOfCoef pe; EntityType EdgesOf; NameOfConstraint Boundary;}
    }
  }
}
Formulation {
  { Name PM; Type FemEquation;
    Quantity {{Name phi; Type Local; NameOfSpace H1;}}
    Equation {
      Galerkin {[permeability[{d phi}]*Dof{d phi},{d phi}]; In Domain; Jacobian J; Integration I;}
      Galerkin {JacNL [tangentNL[{d phi}]*Dof{d phi},{d phi}]; In Plate; Jacobian J; Integration I;}
      Galerkin {[-br[],{d phi}]; In Magnet; Jacobian J; Integration I;}
    }
  }
}
Resolution {
  { Name SolvePM; System {{Name S; NameOfFormulation PM;}}
    Operation {
      InitSolution[S];
      If(Mode==2)
        IterativeLoop[100,1e-9,Relaxation] {GenerateJac[S];SolveJac[S];}
        Print[{$NLResidual,$NLIteration},File "nonlinear.txt",Format "%.17g %.0f"];
        Test[$NLResidual>1e-9] {Error["Nonlinear finite plate failed to converge"];}
      Else
        GenerateJac[S];SolveJac[S];
      EndIf
      SaveSolution[S];PostOperation[Samples];
    }
  }
}
PostProcessing {
  {Name Fields; NameOfFormulation PM;
    Quantity {{Name b; Value {Local {[-permeability[{d phi}]*{d phi}+br[]];In Domain;Jacobian J;}}}}
  }
}
PostOperation {
  {Name Samples; NameOfPostProcessing Fields;
    Operation {
      Print[b,OnLine {{-0.003,0,0.0008}{0.003,0,0.0008}} {24},Format SimpleTable,File "field.txt"];
    }
  }
}
