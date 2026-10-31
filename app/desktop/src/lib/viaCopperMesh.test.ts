import { describe, expect, it } from "vitest";
import { DoubleSide, Mesh, MeshBasicMaterial, Raycaster, Vector3, type BufferGeometry } from "three";
import { annularPadsGeometry, viaBarrelsGeometry, type CopperPad } from "./viaCopperMesh";
import { rectangularCopperGeometry } from "./copperMesh";

const pad = (y = 0, thickness = .035): CopperPad => ({point:new Vector3(0,y,0),thickness,layer:0,net:"A"});
function hits(geometry:BufferGeometry, origin:Vector3, direction=new Vector3(0,-1,0)) {
  const material=new MeshBasicMaterial({side:DoubleSide}), mesh=new Mesh(geometry,material);
  mesh.updateMatrixWorld(true);
  const result=new Raycaster(origin,direction).intersectObject(mesh);
  material.dispose();
  return result;
}

describe("physical via copper",()=>{
  it("gives each annulus the layer copper thickness, including top/bottom and inner/outer walls",()=>{
    for(const thickness of [.018,.035,.07]) for(const zScale of [1,20]){
      const p=pad(-.3,thickness),g=annularPadsGeometry([p],.4,.2,zScale);
      g.computeBoundingBox();
      expect(g.boundingBox!.getSize(new Vector3()).y).toBeCloseTo(thickness,6);
      expect(g.boundingBox!.getCenter(new Vector3()).y).toBeCloseTo(-.3*zScale,6);
      expect(hits(g,new Vector3(0,1,0))).toHaveLength(0);
      expect(hits(g,new Vector3(.15,1,0))[0].point.y).toBeCloseTo(-.3*zScale+thickness/2,6);
      expect(hits(g,new Vector3(0,-.3*zScale,0),new Vector3(1,0,0))[0].point.x).toBeCloseTo(.1,6);
      expect(hits(g,new Vector3(.3,-.3*zScale,0),new Vector3(-1,0,0))[0].point.x).toBeCloseTo(.2,6);
      g.dispose();
    }
  });

  it("trims the full trace width at the pad edge and leaves the drill bore empty",()=>{
    // Crossing the center, rather than only ending there, exercises two cut ends.
    const paths=[{points:[new Vector3(-1,0,0),new Vector3(1,0,0)]}];
    const before=JSON.stringify(paths),p=pad();
    const trace=rectangularCopperGeometry(paths,.2,.035,1,paths,[p],.4);
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
      const g=rectangularCopperGeometry(paths,.2,.07,20,[a,b],[pad()],.4);
      expect(hits(g,new Vector3(0,1,0))).toHaveLength(0);
      const positions=g.getAttribute("position");
      for(let i=0;i<positions.count;i++) expect(Math.hypot(positions.getX(i),positions.getZ(i))).toBeGreaterThan(.198);
      g.dispose();
    }
    expect(JSON.stringify([a,b])).toBe(before);
  });

  it("does not clip copper on a different layer",()=>{
    const paths=[{points:[new Vector3(-1,-.3,0),new Vector3(1,-.3,0)]}];
    const g=rectangularCopperGeometry(paths,.2,.035,1,paths,[pad()],.4);
    expect(hits(g,new Vector3(0,1,0))).not.toHaveLength(0);
    g.dispose();
  });

  it("makes a hollow plated barrel with the configured bore, plating and physical span",()=>{
    const paths=[{points:[new Vector3(0,-.3,0),new Vector3(0,0,0)]}];
    for(const zScale of [1,20]){
      const g=viaBarrelsGeometry(paths,.2,.025,zScale);
      g.computeBoundingBox();
      expect(g.boundingBox!.getSize(new Vector3()).x).toBeCloseTo(.25,6);
      expect(g.boundingBox!.getSize(new Vector3()).y).toBeCloseTo(.3*zScale,6);
      expect(hits(g,new Vector3(0,1,0))).toHaveLength(0);
      expect(hits(g,new Vector3(.1125,1,0))).not.toHaveLength(0);
      expect(hits(g,new Vector3(.15,1,0))).toHaveLength(0);
      g.dispose();
    }
  });
});
