// Finite 3D single-magnet/plate diagnostic, SI. Not a periodic motor row.
SetFactory("OpenCASCADE");
DefineConstant[
  h={0.0008, Name "Mesh/solid size"},
  gapmesh={0.0003, Name "Mesh/gap size"},
  thickness={0.005, Name "Plate/thickness"},
  radius={0.03, Name "Mesh/air radius"}
];
Sphere(1)={0,0,0.002,radius};
Box(2)={-0.0025,-0.0025,0.0013,0.005,0.005,0.003};
Box(3)={-0.006,-0.006,-thickness,0.012,0.012,thickness};
air[]=BooleanDifference{Volume{1};Delete;}{Volume{2,3};};
Coherence;
Physical Volume("air",1)={air[]};
Physical Volume("magnet",2)={2};
Physical Volume("plate",3)={3};
outer[]=Boundary{Volume{air[]};};
skin[]=Boundary{Volume{2,3};};
For i In {0:#skin[]-1}
  outer[]-={skin[i],-skin[i]};
EndFor
Physical Surface("outer",4)={outer[]};
Mesh.MeshSizeFromPoints=0;
Mesh.MeshSizeFromCurvature=12;
Mesh.MeshSizeMin=Min(gapmesh,thickness/3);
Mesh.MeshSizeMax=0.004;
Field[1]=Box;
Field[1].VIn=h;
Field[1].VOut=0.004;
Field[1].XMin=-0.007; Field[1].XMax=0.007;
Field[1].YMin=-0.007; Field[1].YMax=0.007;
Field[1].ZMin=-thickness-0.001; Field[1].ZMax=0.005;
Field[1].Thickness=0.003;
Field[2]=Box;
Field[2].VIn=Min(gapmesh,thickness/3);
Field[2].VOut=0.004;
Field[2].XMin=-0.0035; Field[2].XMax=0.0035;
Field[2].YMin=-0.0035; Field[2].YMax=0.0035;
Field[2].ZMin=-Min(thickness,0.001); Field[2].ZMax=0.0018;
Field[2].Thickness=0.001;
Field[10]=Min;
Field[10].FieldsList={1,2};
Background Field=10;
Mesh.MshFileVersion=2.2;
