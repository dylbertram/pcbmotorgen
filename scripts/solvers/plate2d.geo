// Half-period symmetry of an alternating PM row, SI units.
// A_z has natural side boundaries. Scalar magnetic potential is zero on sides.
SetFactory("OpenCASCADE");
DefineConstant[
  thickness = {0.0002, Name "Plate/thickness"},
  h = {0.00004, Name "Mesh/near size"},
  far = {0.04, Name "Mesh/air extent"}
];
// OCC bounding boxes include its roughly 1e-7 m geometric tolerance.
eps = 1e-6;
Rectangle(1) = {-0.003, -thickness-far, 0, 0.006, thickness+2*far+0.0043};
Rectangle(2) = {-0.0025, 0.0013, 0, 0.005, 0.003};
Rectangle(3) = {-0.003, -thickness, 0, 0.006, thickness};
fragments[] = BooleanFragments{ Surface{1}; Delete; }{ Surface{2,3}; Delete; };
mag[] = Surface In BoundingBox {-0.0025-eps,0.0013-eps,-eps,0.0025+eps,0.0043+eps,eps};
plate[] = Surface In BoundingBox {-0.003-eps,-thickness-eps,-eps,0.003+eps,eps,eps};
If(#mag[] != 1 || #plate[] != 1)
  Error("Expected one magnet and one plate surface");
EndIf
air[] = Surface{:};
air[] -= mag[];
air[] -= plate[];
Physical Surface("air", 1) = {air[]};
Physical Surface("magnet", 2) = {mag[]};
Physical Surface("plate", 3) = {plate[]};
top[] = Curve In BoundingBox {-0.003-eps,far+0.0043-eps,-eps,0.003+eps,far+0.0043+eps,eps};
bottom[] = Curve In BoundingBox {-0.003-eps,-thickness-far-eps,-eps,0.003+eps,-thickness-far+eps,eps};
left[] = Curve In BoundingBox {-0.003-eps,-thickness-far-eps,-eps,-0.003+eps,far+0.0043+eps,eps};
right[] = Curve In BoundingBox {0.003-eps,-thickness-far-eps,-eps,0.003+eps,far+0.0043+eps,eps};
Physical Curve("far", 10) = {top[],bottom[]};
Physical Curve("sides", 11) = {left[],right[]};
If(#top[] < 1 || #bottom[] < 1 || #left[] < 1 || #right[] < 1)
  Error("Missing outer or symmetry boundaries");
EndIf
Mesh.MeshSizeFromPoints = 0;
Mesh.MeshSizeFromCurvature = 0;
Mesh.MeshSizeMax = 0.002;
Mesh.MeshSizeMin = Min(h,thickness/4);
Field[1] = Box;
Field[1].VIn = Min(h,thickness/4);
Field[1].VOut = 0.002;
Field[1].XMin = -0.003;
Field[1].XMax = 0.003;
Field[1].YMin = -0.0006;
Field[1].YMax = 0.001;
Field[1].Thickness = 0.0003;
Field[2] = Box;
Field[2].VIn = Min(h,thickness/4);
Field[2].VOut = 0.002;
Field[2].XMin = -0.003;
Field[2].XMax = 0.003;
// Keep every stress path inside the uniform fine-air band, not on its edge.
Field[2].YMin = -thickness-0.0006;
Field[2].YMax = -thickness+0.0006;
Field[2].Thickness = 0.0003;
Field[3] = Box;
Field[3].VIn = h*4;
Field[3].VOut = 0.002;
Field[3].XMin = -0.003;
Field[3].XMax = 0.003;
Field[3].YMin = -thickness;
Field[3].YMax = 0.0044;
Field[3].Thickness = 0.0003;
Field[10] = Min;
Field[10].FieldsList = {1,2,3};
Background Field = 10;
Mesh.MshFileVersion = 2.2;
