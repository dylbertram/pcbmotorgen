import { describe, expect, it } from "vitest";
import { DoubleSide, Mesh, MeshBasicMaterial, Raycaster, Vector3, type BufferGeometry } from "three";
import { annularPadsGeometry, viaBarrelsGeometry, type CopperPad } from "./viaCopperMesh";
import { rectangularCopperGeometry } from "./copperMesh";
import { buildCoilScene, connectedViaPads } from "./coilScene";

const pad = (y = 0, thickness = .035): CopperPad => ({point:new Vector3(0,y,0),thickness,layer:0,net:"A"});
function hits(geometry:BufferGeometry, origin:Vector3, direction=new Vector3(0,-1,0)) {
  const material=new MeshBasicMaterial({side:DoubleSide}), mesh=new Mesh(geometry,material);
  mesh.updateMatrixWorld(true);
  const result=new Raycaster(origin,direction).intersectObject(mesh);
  material.dispose();
  return result;
}

describe("physical via copper",()=>{
  it("leaves only barrel plating on unconnected layers while retaining connected annuli",()=>{
    const scene=buildCoilScene({trace_width_mm:.2,layer_z_mm:[0,-.16,-.32,-.48,-.64,-.8],routing:{format_version:2,
      segments:[0,2,5].map(layer=>({start:{x:0,y:0},end:{x:1,y:0},layer,net:"A",is_active:true})),curves:[],
      vias:[{position:{x:0,y:0},from_layer:0,to_layer:5,net:"A"}]}})!;
    const pads=connectedViaPads(scene,scene.paths,.4*scene.scale);
    const rings=annularPadsGeometry(pads,.4*scene.scale,.2*scene.scale);
    const barrel=viaBarrelsGeometry(scene.vias,.2*scene.scale,.025*scene.scale);
    for(let layer=0;layer<6;layer++){
      const origin=scene.vias[0].points[0].clone().setX(scene.vias[0].points[0].x+.3*scene.scale).setY(scene.layerY[layer]);
      const ringHits=hits(rings,origin,new Vector3(-1,0,0));
      expect(ringHits.length>0,`annulus on layer ${layer}`).toBe([0,2,5].includes(layer));
      if(![0,2,5].includes(layer)){
        const wall=hits(barrel,origin,new Vector3(-1,0,0))[0];
        expect(wall).toBeDefined();
        expect((wall.point.x-scene.vias[0].points[0].x)/scene.scale).toBeCloseTo(.125,6);
      }
    }
    rings.dispose();barrel.dispose();
  });

  it("gives each annulus the layer copper thickness, including top/bottom and inner/outer walls",()=>{
    for(const thickness of [.018,.035,.07]){
      const p=pad(-.3,thickness),g=annularPadsGeometry([p],.4,.2);
      g.computeBoundingBox();
      expect(g.boundingBox!.getSize(new Vector3()).y).toBeCloseTo(thickness,6);
      expect(g.boundingBox!.getCenter(new Vector3()).y).toBeCloseTo(-.3,6);
      expect(hits(g,new Vector3(0,1,0))).toHaveLength(0);
      expect(hits(g,new Vector3(.15,1,0))[0].point.y).toBeCloseTo(-.3+thickness/2,6);
      expect(hits(g,new Vector3(0,-.3,0),new Vector3(1,0,0))[0].point.x).toBeCloseTo(.1,6);
      expect(hits(g,new Vector3(.3,-.3,0),new Vector3(-1,0,0))[0].point.x).toBeCloseTo(.2,6);
      g.dispose();
    }
  });

  it("trims the full trace width at the pad edge and leaves the drill bore empty",()=>{
    // Crossing the center, rather than only ending there, exercises two cut ends.
    const paths=[{points:[new Vector3(-1,0,0),new Vector3(1,0,0)]}];
    const before=JSON.stringify(paths),p=pad();
    const trace=rectangularCopperGeometry(paths,.2,.035,paths,[p],.4);
    for(let x=-.16;x<=.16;x+=.04) for(let z=-.08;z<=.08;z+=.04){
      expect(hits(trace,new Vector3(x,1,z)),`no trace inside pad at ${x}, ${z}`).toHaveLength(0);
    }
    expect(hits(trace,new Vector3(.3,1,0))).not.toHaveLength(0);
    expect(hits(trace,new Vector3(.3,1,.12))).toHaveLength(0);
    // Both surfaces meet at the identical polygon, with no missing connector.
    const annulus=annularPadsGeometry([p],.4,.2);
    for(const x of [.12,.18,.22,.3]) expect(hits(trace,new Vector3(x,1,0)).length+hits(annulus,new Vector3(x,1,0)).length).toBeGreaterThan(0);
    expect(JSON.stringify(paths)).toBe(before);
    trace.dispose();annulus.dispose();
  });

  it("clips diagonal finite-width ends and retains their original centerlines and heat-batch joins",()=>{
    const a={points:[new Vector3(-1,0,-1),new Vector3(0,0,0)]};
    const b={points:[new Vector3(0,0,0),new Vector3(1,0,0)]};
    const before=JSON.stringify([a,b]);
    for(const paths of [[a,b],[a],[b]]){
      const g=rectangularCopperGeometry(paths,.2,.07,[a,b],[pad()],.4);
      expect(hits(g,new Vector3(0,1,0))).toHaveLength(0);
      const positions=g.getAttribute("position");
      for(let i=0;i<positions.count;i++) expect(Math.hypot(positions.getX(i),positions.getZ(i))).toBeGreaterThan(.198);
      g.dispose();
    }
    expect(JSON.stringify([a,b])).toBe(before);
  });

  it("does not clip copper on a different layer",()=>{
    const paths=[{points:[new Vector3(-1,-.3,0),new Vector3(1,-.3,0)]}];
    const g=rectangularCopperGeometry(paths,.2,.035,paths,[pad()],.4);
    expect(hits(g,new Vector3(0,1,0))).not.toHaveLength(0);
    g.dispose();
  });

  it("makes a hollow plated barrel with the configured bore, plating and physical span",()=>{
    const paths=[{points:[new Vector3(0,-.3,0),new Vector3(0,0,0)]}];
    const g=viaBarrelsGeometry(paths,.2,.025);
    g.computeBoundingBox();
    expect(g.boundingBox!.getSize(new Vector3()).x).toBeCloseTo(.25,6);
    expect(g.boundingBox!.getSize(new Vector3()).y).toBeCloseTo(.3,6);
    expect(hits(g,new Vector3(0,1,0))).toHaveLength(0);
    expect(hits(g,new Vector3(.1125,1,0))).not.toHaveLength(0);
    expect(hits(g,new Vector3(.15,1,0))).toHaveLength(0);
    g.dispose();
  });
});
