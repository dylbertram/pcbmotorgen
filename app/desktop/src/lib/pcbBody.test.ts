import { expect, it } from "vitest";
import type { CadGeometry } from "./types";
import { buildCoilScene } from "./coilScene";
import { pcbBody } from "./pcbBody";
import { pcbStackupHeightsMm } from "./pcbStackup";

it("places the body between the physical outer copper planes and never changes copper", () => {
  const g: CadGeometry = { trace_width_mm: .2, layer_z_mm: [0, -.8], routing: { format_version: 1, curves: [], vias: [], segments: [
    { start: { x: 0, y: 0 }, end: { x: 20, y: 8 }, layer: 0, net: "A", is_active: true },
    { start: { x: 0, y: 0 }, end: { x: 20, y: 8 }, layer: 1, net: "A", is_active: true },
  ] } };
  const before = JSON.stringify(g), scene = buildCoilScene(g)!;
  for (const zScale of [1, 20]) {
    const board = pcbBody(g, scene, .8, zScale);
    expect(board.position[1] + board.size[1] / 2).toBeCloseTo(scene.paths[0].points[0].y * zScale);
    expect(board.position[1] - board.size[1] / 2).toBeCloseTo(scene.paths[1].points[0].y * zScale);
    expect(board.size[0] / scene.scale).toBeCloseTo(22.2);
  }
  expect(JSON.stringify(g)).toBe(before);
  expect(() => pcbBody(g, scene, -1)).toThrow();
});

it("custom board surfaces enclose copper centers and retain the full stack thickness", () => {
  const stack = {copper_mm:[.035,.018,.070,.035],dielectric_mm:[.1,.4,.142]};
  const g:CadGeometry = {trace_width_mm:.2,layer_z_mm:pcbStackupHeightsMm(stack),routing:{format_version:2,curves:[],vias:[{position:{x:20,y:8},from_layer:0,to_layer:3,net:"A"}],segments:
    stack.copper_mm.map((_,layer)=>({start:{x:0,y:0},end:{x:20,y:8},layer,net:"A",is_active:true}))}};
  const scene=buildCoilScene(g,{outer:.1,inner:.1,layers:stack.copper_mm})!;
  scene.thicknessByLayer.forEach((thickness,layer)=>expect(thickness/scene.scale).toBeCloseTo(stack.copper_mm[layer],12));
  expect((scene.vias[0].points[0].y-scene.vias[0].points[1].y)/scene.scale).toBeCloseTo(.765,12);
  for(const zScale of [1,20]){
    const body=pcbBody(g,scene,.8,zScale,0);
    const physical=(y:number)=>y/scene.scale/zScale+scene.centerMm[1];
    expect(physical(body.position[1]+body.size[1]/2)).toBeCloseTo(0,12);
    expect(physical(body.position[1]-body.size[1]/2)).toBeCloseTo(-.8,12);
  }
});
