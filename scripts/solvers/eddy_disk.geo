// Finite conducting disk in a uniform harmonic applied field. SI units.
SetFactory("OpenCASCADE");
DefineConstant[
  a={0.006,Name "Disk/radius"},
  thickness={0.001,Name "Disk/thickness"},
  h={0.0008,Name "Mesh/conductor"},
  radius={0.03,Name "Mesh/air radius"},
  far_mesh={0.004,Name "Mesh/far air size"},
  slot={0,Name "Disk/radial slot width"}
];
Sphere(1)={0,0,0,radius};
Cylinder(2)={0,0,-thickness/2,0,0,thickness,a};
disk[]={2};
If(slot>0)
  Box(3)={0,-slot/2,-thickness,2*a,slot,2*thickness};
  disk[]=BooleanDifference{Volume{2};Delete;}{Volume{3};Delete;};
EndIf
air[]=BooleanDifference{Volume{1};Delete;}{Volume{disk[]};};
Coherence;
Physical Volume("air",1)={air[]};
Physical Volume("conductor",2)={disk[]};
outer[]=Boundary{Volume{air[]};};
skin[]=Boundary{Volume{disk[]};};
For i In {0:#skin[]-1}
  outer[]-={skin[i],-skin[i]};
EndFor
Physical Surface("outer",3)={outer[]};
Physical Surface("conductor_surface",4)={skin[]};
Mesh.MeshSizeFromPoints=0;
Mesh.MeshSizeFromCurvature=48;
Mesh.MeshSizeMin=Min(h,thickness/3);
Mesh.MeshSizeMax=far_mesh;
Field[1]=Box;
Field[1].VIn=Min(h,thickness/3);
Field[1].VOut=far_mesh;
Field[1].XMin=-a-0.0003;Field[1].XMax=a+0.0003;
Field[1].YMin=-a-0.0003;Field[1].YMax=a+0.0003;
Field[1].ZMin=-thickness/2-0.0003;Field[1].ZMax=thickness/2+0.0003;
Field[1].Thickness=0.001;
Background Field=1;
Mesh.MshFileVersion=2.2;
