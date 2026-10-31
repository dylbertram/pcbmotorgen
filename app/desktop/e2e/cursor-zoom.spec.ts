import { test, expect, type Locator } from "@playwright/test";
import { OrthographicCamera, Vector3 } from "three";
import { gotoDesignApp, openCoilPreview } from "./helpers";
import { installViewMenu } from "./view-menu-helpers";

const views = [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]];
interface Snapshot { position: number[]; target: number[]; zoom: number }
interface Rect { x: number; y: number; width: number; height: number }
async function drawingRect(viewer: Locator): Promise<Rect> {
  const canvas = viewer.locator("canvas");
  // Renderer canvas dimensions follow the view's inset layout via ResizeObserver.
  await expect.poll(async () => {
    const c = (await canvas.boundingBox())!, v = (await viewer.boundingBox())!;
    return Math.abs(c.width - v.width) + Math.abs(c.height - v.height);
  }).toBeLessThan(.5);
  return (await canvas.boundingBox())!;
}
function cameraFor(state: Snapshot, rect: Rect, mode: string) {
  const camera = new OrthographicCamera(-rect.width / 2, rect.width / 2, rect.height / 2, -rect.height / 2, .01, mode === "top" ? 2000 : 1000);
  camera.position.fromArray(state.position); camera.up.set(0, mode === "top" ? 0 : 1, mode === "top" ? -1 : 0);
  camera.lookAt(new Vector3().fromArray(state.target)); camera.zoom = state.zoom;
  camera.updateProjectionMatrix(); camera.updateMatrixWorld(true); return camera;
}
function worldAt(state: Snapshot, rect: Rect, mode: string, x: number, y: number) {
  const camera = cameraFor(state, rect, mode), depth = new Vector3().fromArray(state.target).project(camera).z;
  return new Vector3(x * 2 - 1, 1 - y * 2, depth).unproject(camera);
}
function anchorError(world: Vector3, state: Snapshot, rect: Rect, mode: string, x: number, y: number) {
  const point = world.clone().project(cameraFor(state, rect, mode));
  return Math.hypot(((point.x + 1) / 2 - x) * rect.width, ((1 - point.y) / 2 - y) * rect.height);
}

test.beforeEach(async ({ page }) => { await installViewMenu(page); });

test("two-finger trackpad scrolling pans without zooming or orbiting in every view", async ({ page }) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  for (const [label, id] of views) {
    await page.getByRole("button", { name: label, exact: true }).click();
    const viewer = page.getByTestId(`coil-${id}`);
    await expect(viewer).toHaveAttribute("data-camera", /position/);
    const rect = await drawingRect(viewer);
    const snapshot = async () => JSON.parse((await viewer.getAttribute("data-camera"))!) as Snapshot;
    for (const [dx, dy] of [[48, 64], [-28, -36]]) {
      const x = .62, y = .4, before = await snapshot(), world = worldAt(before, rect, id, x, y);
      await page.mouse.move(rect.x + rect.width * x, rect.y + rect.height * y);
      await page.mouse.wheel(dx, dy);
      await expect.poll(async () => (await snapshot()).target).not.toEqual(before.target);
      expect((await snapshot()).zoom).toBeCloseTo(before.zoom, 10);
      const angle = (state: Snapshot) => new Vector3().fromArray(state.position).sub(new Vector3().fromArray(state.target)).normalize();
      expect(angle(await snapshot()).distanceTo(angle(before))).toBeLessThan(1e-10);
      await expect.poll(async () => anchorError(world, await snapshot(), rect, id, x - dx / rect.width, y - dy / rect.height)).toBeLessThan(1);
    }
  }
});

test("trackpad pinch keeps an off-center world point under the cursor in every view", async ({ page }) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  for (const [label, id] of views) {
    await page.getByRole("button", { name: label, exact: true }).click();
    const viewer = page.getByTestId(`coil-${id}`);
    await expect(viewer).toHaveAttribute("data-camera", /position/);
    const rect = await drawingRect(viewer);
    const snapshot = async () => JSON.parse((await viewer.getAttribute("data-camera"))!) as Snapshot;
    for (const delta of [-80, 80]) {
      const x = .7, y = .35, before = await snapshot(), world = worldAt(before, rect, id, x, y);
      await page.mouse.move(rect.x + rect.width * x, rect.y + rect.height * y);
      await page.keyboard.down("Control");
      await page.mouse.wheel(0, delta);
      await page.keyboard.up("Control");
      await expect.poll(async () => (await snapshot()).zoom).not.toBe(before.zoom);
      if (delta < 0) expect((await snapshot()).zoom).toBeGreaterThan(before.zoom);
      else expect((await snapshot()).zoom).toBeLessThan(before.zoom);
      await expect.poll(async () => anchorError(world, await snapshot(), rect, id, x, y)).toBeLessThan(1);
      await test.info().attach(`${id}-pinch-${delta}.json`, { contentType: "application/json", body: JSON.stringify({ before, after: await snapshot(), rect, anchor: world.toArray(), error: anchorError(world, await snapshot(), rect, id, x, y) }) });
    }
  }
});

test.describe("touch pinch", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test("parallel two-finger touch motion pans the 3D view without zooming or orbiting", async ({ page }) => {
    await gotoDesignApp(page); await openCoilPreview(page);
    await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
    const viewer = page.getByTestId("coil-iso");
    await expect(viewer).toHaveAttribute("data-camera", /position/);
    const rect = await drawingRect(viewer), snapshot = async () => JSON.parse((await viewer.getAttribute("data-camera"))!) as Snapshot;
    const x = .6, y = .43, before = await snapshot(), world = worldAt(before, rect, "iso", x, y);
    const touch = await page.context().newCDPSession(page);
    const points = (dx: number, dy: number) => [-18, 18].map((offset, id) => ({ id, x: rect.x + rect.width * x + offset + dx, y: rect.y + rect.height * y + dy }));
    await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points(0, 0) });
    await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: points(24, 32) });
    await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await expect.poll(async () => anchorError(world, await snapshot(), rect, "iso", x + 24 / rect.width, y + 32 / rect.height)).toBeLessThan(1);
    const after = await snapshot();
    // CDP rounds touch positions to subpixels, slightly perturbing finger separation.
    expect(Math.abs(after.zoom / before.zoom - 1)).toBeLessThan(1e-6);
    const direction = (state: Snapshot) => new Vector3().fromArray(state.position).sub(new Vector3().fromArray(state.target)).normalize();
    expect(direction(after).distanceTo(direction(before))).toBeLessThan(1e-10);
    await touch.detach();
  });
  test("pinching uses the touch midpoint, not the viewport center or stale mouse position", async ({ page }) => {
    await gotoDesignApp(page); await openCoilPreview(page);
    const touch = await page.context().newCDPSession(page);
    for (const [label, id] of views) {
      await page.getByRole("button", { name: label, exact: true }).click();
      const viewer = page.getByTestId(`coil-${id}`);
      await expect(viewer).toHaveAttribute("data-camera", /position/);
      const rect = await drawingRect(viewer);
      const snapshot = async () => JSON.parse((await viewer.getAttribute("data-camera"))!) as Snapshot;
      const x = .68, y = .43, before = await snapshot(), world = worldAt(before, rect, id, x, y);
      await page.mouse.move(rect.x + rect.width * .3, rect.y + rect.height * .7);
      // Top keeps its CAD convention: two-finger pan, three-finger zoom.
      const offsets = id === "top" ? [[-18, -9], [18, -9], [0, 18]] : [[-18, 0], [18, 0]];
      const points = (scale: number) => offsets.map(([dx, dy], index) => ({ id: index, x: rect.x + rect.width * x + dx * scale, y: rect.y + rect.height * y + dy * scale }));
      await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points(1) });
      await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: points(1.6) });
      await expect.poll(async () => (await snapshot()).zoom).toBeGreaterThan(before.zoom);
      await expect.poll(async () => anchorError(world, await snapshot(), rect, id, x, y)).toBeLessThan(1);
      await test.info().attach(`${id}-touch.json`, { contentType: "application/json", body: JSON.stringify({ before, after: await snapshot(), rect, anchor: world.toArray(), error: anchorError(world, await snapshot(), rect, id, x, y) }) });
      await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: points(1) });
      await expect.poll(async () => (await snapshot()).zoom).toBeCloseTo(before.zoom, 5);
      await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await expect.poll(async () => anchorError(world, await snapshot(), rect, id, x, y)).toBeLessThan(1);
    }
    await touch.detach();
  });
});
