// SI-unit free-space PM benchmark, shared by GetDP and Elmer prototypes.
// Physical tags: 1 air, 2 magnet, 3 outer boundary. No housing physics yet.
SetFactory("OpenCASCADE");
DefineConstant[
  h = {0.0004, Name "Mesh/near size"},
  radius = {0.03, Name "Mesh/air radius"}
];
Sphere(1) = {0, 0, 0.002, radius};
Box(2) = {-0.0025, -0.0025, 0.0005, 0.005, 0.005, 0.003};
air[] = BooleanDifference{ Volume{1}; Delete; }{ Volume{2}; };
Coherence;
Physical Volume("air", 1) = {air[]};
Physical Volume("magnet", 2) = {2};
outer[] = Surface In BoundingBox {-radius-1e-6,-radius-1e-6,0.002-radius-1e-6,radius+1e-6,radius+1e-6,0.002+radius+1e-6};
skin[] = Boundary{ Volume{2}; };
For i In {0:#skin[]-1}
  outer[] -= {Abs(skin[i])};
EndFor
Physical Surface("outer", 3) = {outer[]};
Mesh.MeshSizeMin = h;
Mesh.MeshSizeMax = 0.003;
Mesh.MeshSizeFromCurvature = 12;
Field[1] = Box;
Field[1].VIn = h;
Field[1].VOut = 0.003;
Field[1].XMin = -0.004;
Field[1].XMax = 0.004;
Field[1].YMin = -0.004;
Field[1].YMax = 0.004;
Field[1].ZMin = -0.002;
Field[1].ZMax = 0.005;
Field[1].Thickness = 0.005;
Background Field = 1;
Mesh.MshFileVersion = 2.2;
