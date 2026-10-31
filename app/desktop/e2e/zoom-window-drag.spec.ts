import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp, openCoilPreview } from "./helpers";
import { installViewMenu } from "./view-menu-helpers";

const views = [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]];
async function selectWindow(page: Page, label: string, id: string) {
  await page.getByRole("button", { name: label, exact: true }).click();
  const viewer = page.getByTestId(`coil-${id}`);
  await expect(viewer).toHaveAttribute("data-camera", /position/);
  const camera = (await viewer.getAttribute("data-camera"))!;
  await page.getByRole("button", { name: "Zoom window", exact: true }).click();
  const picker = page.getByRole("button", { name: "Pick zoom window corners", exact: true });
  return { viewer, camera, picker, rect: (await picker.boundingBox())! };
}

test.beforeEach(async ({ page }) => { await installViewMenu(page); });

test("dragging fits on release without moving the camera during selection in every view", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  for (const [label, id] of views) {
    const { viewer, camera, picker, rect } = await selectWindow(page, label, id);
    const counts = await viewer.evaluate(el => ["data-segments", "data-vias", "data-layers"].map(key => el.getAttribute(key)));
    const a = id === "left" ? [.65, .6] : [.35, .35], b = id === "left" ? [.35, .35] : [.65, .6];
    await page.mouse.move(rect.x + rect.width * a[0], rect.y + rect.height * a[1]);
    await page.mouse.down();
    await page.mouse.move(rect.x + rect.width * b[0], rect.y + rect.height * b[1], { steps: 10 });
    await expect(picker).toContainText("Release to zoom");
    expect(Number(await picker.locator("svg rect").getAttribute("width"))).toBeCloseTo(30, 3);
    expect(Number(await picker.locator("svg rect").getAttribute("height"))).toBeCloseTo(25, 3);
    await expect(viewer).toHaveAttribute("data-camera", camera);
    if (id === "iso") await page.screenshot({ path: info.outputPath("drag-window-before-release.png") });
    await page.mouse.up();
    await expect(picker).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Zoom window", exact: true })).toHaveAttribute("aria-pressed", "false");
    const before = JSON.parse(camera);
    await expect.poll(async () => JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(before.zoom);
    const after = JSON.parse((await viewer.getAttribute("data-camera"))!);
    expect(after.target).not.toEqual(before.target);
    const direction = (s: typeof before) => { const d = s.position.map((v: number, i: number) => v - s.target[i]); return d.map((v: number) => v / Math.hypot(...d)); };
    direction(after).forEach((v: number, i: number) => expect(v).toBeCloseTo(direction(before)[i], 9));
    expect(await viewer.evaluate(el => ["data-segments", "data-vias", "data-layers"].map(key => el.getAttribute(key)))).toEqual(counts);
  }
});

test("tiny drags and Escape during a held drag never fit or navigate", async ({ page }) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  for (const [label, id] of views) {
    const { viewer, camera, picker, rect } = await selectWindow(page, label, id);
    const x = rect.x + rect.width * .4, y = rect.y + rect.height * .4;
    await page.mouse.move(x, y); await page.mouse.down();
    await page.mouse.move(x + 2, y + 2); await page.mouse.up();
    await expect(picker).toBeVisible(); await expect(viewer).toHaveAttribute("data-camera", camera);
    await page.keyboard.press("Escape"); await expect(picker).toHaveCount(0);
    await page.getByRole("button", { name: "Zoom window", exact: true }).click();
    await page.mouse.move(x, y); await page.mouse.down();
    await page.mouse.move(x + rect.width * .2, y + rect.height * .2, { steps: 8 });
    await page.keyboard.press("Escape");
    await expect(picker).toHaveCount(0);
    await page.mouse.up(); await page.mouse.move(x, y);
    await expect(viewer).toHaveAttribute("data-camera", camera);
  }
});

test("captured drag can finish beyond the viewport edge", async ({ page }) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  const { viewer, camera, picker, rect } = await selectWindow(page, "3D fields and heat", "iso");
  await page.mouse.move(rect.x + rect.width * .35, rect.y + rect.height * .3); await page.mouse.down();
  await page.mouse.move(rect.x + rect.width + 20, rect.y + rect.height + 12, { steps: 10 });
  await expect(picker).toContainText("Release to zoom");
  await expect(viewer).toHaveAttribute("data-camera", camera);
  await page.mouse.up(); await expect(picker).toHaveCount(0);
  await expect.poll(async () => JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(JSON.parse(camera).zoom);
});

test.describe("touch selection", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test("touch drag fits and a cancelled touch preserves the camera and two-tap selection", async ({ page }) => {
    await gotoDesignApp(page); await openCoilPreview(page);
    const touch = await page.context().newCDPSession(page);
    for (const [label, id] of [views[0], views[3]]) {
      const { viewer, camera, picker, rect } = await selectWindow(page, label, id);
      const a = { x: rect.x + rect.width * .35, y: rect.y + rect.height * .35 }, b = { x: rect.x + rect.width * .65, y: rect.y + rect.height * .65 };
      await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [a] });
      await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [b] });
      await expect(picker).toContainText("Release to zoom");
      await touch.send("Input.dispatchTouchEvent", { type: "touchCancel", touchPoints: [] });
      await expect(picker).toContainText("Drag a window or click two corners");
      await expect(viewer).toHaveAttribute("data-camera", camera);
      await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [a] });
      await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [b] });
      await expect(viewer).toHaveAttribute("data-camera", camera);
      await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await expect(picker).toHaveCount(0);
      await expect.poll(async () => JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(JSON.parse(camera).zoom);
      await page.getByRole("button", { name: "Zoom window", exact: true }).click();
      await page.touchscreen.tap(a.x, a.y);
      await expect(picker).toContainText("Choose the opposite corner");
      await page.touchscreen.tap(b.x, b.y); await expect(picker).toHaveCount(0);
    }
    await touch.detach();
  });
});
