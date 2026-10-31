import { it, expect } from "vitest";
import { previewCopperKeys } from "./previewCopperKeys";
import type { CadGeometry, CoilPathDto } from "./types";

it("one-period filtering keeps native scene keys and never reindexes heat geometry",()=>{
  const first={start:[0,0],end:[.001,0],is_active:true};
  const second={start:[.001,0],end:[.002,0],is_active:true};
  const coils={phases:[{phase_name:"A",phase_idx:0,layer_idx:0,segments:[first,second],corner_arcs:[]}]} as unknown as CoilPathDto;
  const geometry={routing:{segments:[{start:{x:0,y:0},end:{x:1,y:0},layer:0,net:"A"},{start:{x:1,y:0},end:{x:2,y:0},layer:0,net:"A"}],curves:[],vias:[]}} as unknown as CadGeometry;
  const before=JSON.stringify(geometry);
  expect([...previewCopperKeys(geometry,coils,new Map([[0,[coils.phases[0].segments[1]]]]),new Map())]).toEqual(["segment-1"]);
  expect(JSON.stringify(geometry)).toBe(before);
});
