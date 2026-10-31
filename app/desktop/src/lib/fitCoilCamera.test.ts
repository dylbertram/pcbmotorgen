import { describe, expect, it } from "vitest";
import { Box3, BoxGeometry, Group, Mesh, MeshBasicMaterial, OrthographicCamera, Vector3 } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fitCoilCamera, fitCoilWindow, coilWindowFocus, stopCoilCameraMotion, alignTopCamera } from "./fitCoilCamera";

describe("coil viewer camera fitting", () => {
  it("projects top copper onto the exact same pixel transform as the editing overlays", () => {
    const scene={scale:.1,centerMm:[40,-.4,-5] as [number,number,number]};
    for(const [width,height] of [[1000,500],[390,700]]) {
      const top={transform:{s:5000,tx:70,ty:180},panX:23,panY:-11,width:760,height:height*760/width};
      const camera=new OrthographicCamera();alignTopCamera(camera,scene,top,width,height);
      for(const [x,y,z] of [[0,0,0],[.05,.008,-.0008],[.09,.02,-.0002]]) {
        const point=new Vector3((x*1000-40)*.1,(z*1000+.4)*.1,(-y*1000+5)*.1).project(camera);
        expect((point.x+1)*width/2).toBeCloseTo((70+23+5000*x)*width/760,8);
        expect((1-point.y)*height/2).toBeCloseTo((180-11-5000*y)*width/760,8);
      }
      expect(camera.getWorldDirection(new Vector3()).y).toBeCloseTo(-1,12);
    }
  });
  const box = new Box3(new Vector3(-6, -.1, -1), new Vector3(6, .1, 1));
  it("cancels residual orbit motion without moving the displayed camera or pivot", () => {
    const camera = new OrthographicCamera();
    const target = fitCoilCamera(camera, box, 1000, 500, new Vector3(12, 10, 14))!;
    const controls = new OrbitControls(camera);
    controls.target.copy(target); controls.enableDamping = true;
    // Seed the same residual orbit/pan state left by a pointer drag.
    const pending = controls as unknown as {_sphericalDelta:{theta:number;phi:number};_panOffset:Vector3};
    pending._sphericalDelta.theta=.4; pending._sphericalDelta.phi=.1; pending._panOffset.set(2,1,0);
    const position=camera.position.clone(), pivot=controls.target.clone(), direction=camera.getWorldDirection(new Vector3()), zoom=camera.zoom;
    stopCoilCameraMotion(camera,controls);
    controls.update();
    expect(camera.position.distanceTo(position)).toBeLessThan(1e-10);
    expect(controls.target.distanceTo(pivot)).toBeLessThan(1e-10);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(direction)).toBeLessThan(1e-12);
    expect(camera.zoom).toBe(zoom); expect(controls.enableDamping).toBe(true);
    // No DOM element was connected, so there are no listeners to dispose.
  });
  it("looks squarely at the XZ section instead of retaining isometric angles", () => {
    const camera = new OrthographicCamera();
    fitCoilCamera(camera, box, 1000, 500, new Vector3(12, 10, 14));
    fitCoilCamera(camera, box, 1000, 500, new Vector3(0, 0, 1));
    const direction = camera.getWorldDirection(new Vector3());
    expect(direction.x).toBeCloseTo(0, 12); expect(direction.y).toBeCloseTo(0, 12); expect(direction.z).toBeCloseTo(-1, 12);
    const first = new Vector3(-6, 0, 0).project(camera), last = new Vector3(6, 0, 0).project(camera);
    expect(first.y).toBeCloseTo(last.y, 12);
  });
  it("fits all corners in wide and narrow viewers, including exaggerated display height", () => {
    const before = box.clone();
    for (const [width, height] of [[1000, 300], [240, 600]]) for (const direction of [new Vector3(0, 0, 1), new Vector3(12, 10, 14)]) {
      const camera = new OrthographicCamera();
      const tall = box.clone(); tall.max.y = 20;
      fitCoilCamera(camera, tall, width, height, direction);
      for (const x of [tall.min.x, tall.max.x]) for (const y of [tall.min.y, tall.max.y]) for (const z of [tall.min.z, tall.max.z]) {
        const p = new Vector3(x, y, z).project(camera);
        expect(Math.abs(p.x)).toBeLessThanOrEqual(.800001); expect(Math.abs(p.y)).toBeLessThanOrEqual(.800001);
        expect(Math.abs(p.z)).toBeLessThan(1);
      }
    }
    expect(box).toEqual(before);
  });
  it("does not change the camera for empty or unmeasured scenes", () => {
    const camera = new OrthographicCamera(), before = camera.clone();
    expect(fitCoilCamera(camera, new Box3(), 1000, 500, new Vector3(0, 0, 1))).toBeNull();
    expect(fitCoilCamera(camera, box, 0, 500, new Vector3(0, 0, 1))).toBeNull();
    expect(camera.position).toEqual(before.position); expect(camera.zoom).toBe(before.zoom);
  });
  it("fits a window, preserves the angle and moves the orbit pivot to its center", () => {
    for (const direction of [new Vector3(12, 10, 14), new Vector3(0, 0, 1), new Vector3(-1, 0, 0)]) {
      const camera = new OrthographicCamera();
      const target = fitCoilCamera(camera, box, 1000, 500, direction)!;
      const oldDirection = camera.getWorldDirection(new Vector3()), oldZoom = camera.zoom;
      const depth = target.clone().project(camera).z;
      const corners = [new Vector3(-.8, -.2, depth).unproject(camera), new Vector3(-.4, .6, depth).unproject(camera)];
      const pivot = fitCoilWindow(camera, target, [.1, .6], [.3, .2])!;
      expect(pivot.distanceTo(corners[0].clone().add(corners[1]).multiplyScalar(.5))).toBeLessThan(1e-10);
      expect(pivot.clone().project(camera).length()).toBeGreaterThanOrEqual(0);
      expect(pivot.clone().project(camera).x).toBeCloseTo(0, 12);
      expect(pivot.clone().project(camera).y).toBeCloseTo(0, 12);
      expect(camera.getWorldDirection(new Vector3()).distanceTo(oldDirection)).toBeLessThan(1e-12);
      expect(camera.zoom).toBeCloseTo(oldZoom * 2.5);
      expect(Math.abs(corners[0].project(camera).y)).toBeCloseTo(1, 12);
    }
  });
  it("leaves the view unchanged for a degenerate window", () => {
    const camera = new OrthographicCamera(), before = camera.clone();
    expect(fitCoilWindow(camera, new Vector3(), [0, 0], [0, .5])).toBeNull();
    expect(camera.position).toEqual(before.position); expect(camera.zoom).toEqual(before.zoom);
  });
  it("focuses an off-center window on the actual copper depth, not the old pivot plane", () => {
    const camera = new OrthographicCamera(), content = new Group();
    const geometry = new BoxGeometry(12, .02, 2), material = new MeshBasicMaterial();
    const copper = new Mesh(geometry, material); copper.userData = {measureable:true,copperLayerY:0};
    content.add(copper);
    const target = fitCoilCamera(camera, box, 1000, 500, new Vector3(12, 10, 14))!;
    const angle = camera.getWorldDirection(new Vector3());
    const a: [number, number] = [.5, .35], b: [number, number] = [.7, .55];
    const oldPlane = fitCoilWindow(camera.clone(), target, a, b)!;
    expect(Math.abs(oldPlane.y)).toBeGreaterThan(.1);
    const focus = coilWindowFocus(camera, content, a, b)!;
    expect(Math.abs(focus.y)).toBeLessThanOrEqual(.010001);
    const pivot = fitCoilWindow(camera, target, a, b, focus)!;
    expect(pivot.distanceTo(focus)).toBeLessThan(1e-10);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(angle)).toBeLessThan(1e-12);
    expect(pivot.clone().project(camera).x).toBeCloseTo(0, 12);
    expect(pivot.clone().project(camera).y).toBeCloseTo(0, 12);
    geometry.dispose(); material.dispose();
  });
  it("uses the copper plane in trace gaps and ignores hidden surfaces and annotations", () => {
    const camera = new OrthographicCamera(), content = new Group();
    const geometry = new BoxGeometry(1, .02, 1), material = new MeshBasicMaterial();
    const copper = new Mesh(geometry, material); copper.position.x = -5; copper.userData = {measureable:true,copperLayerY:0};
    const hidden = new Mesh(geometry, material); hidden.position.y = 3; hidden.visible = false; hidden.userData.measureable = true;
    const annotation = new Mesh(geometry, material); annotation.position.y = 2;
    content.add(copper, hidden, annotation);
    fitCoilCamera(camera, box, 1000, 500, new Vector3(12, 10, 14));
    const focus = coilWindowFocus(camera, content, [.5, .4], [.7, .6])!;
    expect(focus.y).toBeCloseTo(0, 12);
    // Edge-on empty space must not use the ray origin as the orbit target.
    fitCoilCamera(camera, box, 1000, 500, new Vector3(0, 0, 1));
    expect(coilWindowFocus(camera, content, [.5, .4], [.7, .6])).toBeNull();
    geometry.dispose(); material.dispose();
  });
});
