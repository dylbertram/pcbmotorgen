import { test, expect } from "@playwright/test";
import { gotoDesignApp, openCoilPreview } from "./helpers";
import { installViewMenu, nativeViewAction } from "./view-menu-helpers";

test.beforeEach(async ({ page }) => { await installViewMenu(page); });

test("3D keeps the toolbar, renders flat copper and toggles the PCB without changing copper", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  const viewer = page.getByTestId("coil-iso");
  await expect(viewer.locator("canvas")).toBeVisible();
  await expect(viewer).toHaveAttribute("data-camera", /position/);
  await expect(viewer).toHaveAttribute("data-copper-section", "rectangular");
  await expect(page.getByRole("toolbar", { name: "Coil preview tools", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit segments", exact: true })).toBeDisabled();
  const counts = await viewer.evaluate(e => [e.getAttribute("data-segments"), e.getAttribute("data-vias"), e.getAttribute("data-layers")]);
  const camera = await viewer.getAttribute("data-camera");
  expect(Number(counts[0])).toBeGreaterThan(0);
  await nativeViewAction(page, "view:pcb");
  await expect(viewer).toHaveAttribute("data-pcb-visible", "true");
  expect(await viewer.evaluate(e => [e.getAttribute("data-segments"), e.getAttribute("data-vias"), e.getAttribute("data-layers")])).toEqual(counts);
  await expect(viewer).toHaveAttribute("data-camera", camera!);
  await page.screenshot({ path: info.outputPath("rectangular-copper-and-pcb.png") });
  await nativeViewAction(page, "view:pcb");
  await expect(viewer).toHaveAttribute("data-pcb-visible", "false");
});

test("3D picks physical spatial distances and keeps the result through orbiting", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await nativeViewAction(page, "view:pcb");
  const viewer = page.getByTestId("coil-iso"), canvas = viewer.locator("canvas");
  await expect(canvas).toBeVisible();
  await expect(viewer).toHaveAttribute("data-camera", /position/);
  await page.getByRole("button", { name: "Toggle measure tool", exact: true }).click();
  const rect = (await canvas.boundingBox())!;
  // The body provides a continuous, physical picking surface through the center.
  await page.mouse.click(rect.x + rect.width * .45, rect.y + rect.height * .5);
  await expect(viewer).toHaveAttribute("data-measure-points", "1");
  await page.mouse.click(rect.x + rect.width * .55, rect.y + rect.height * .5);
  await expect(viewer).toHaveAttribute("data-measure-points", "2");
  const distance = await viewer.getAttribute("data-measure-mm");
  expect(Number(distance)).toBeGreaterThan(0);
  await page.mouse.move(rect.x + rect.width * .8, rect.y + rect.height * .2);
  await page.mouse.down(); await page.mouse.move(rect.x + rect.width * .85, rect.y + rect.height * .25, { steps: 8 }); await page.mouse.up();
  await expect(viewer).toHaveAttribute("data-measure-points", "2");
  await expect(viewer).toHaveAttribute("data-measure-mm", distance!);
  await page.screenshot({ path: info.outputPath("3d-measure-physical-distance.png") });
  await page.getByRole("button", { name: "Clear measurement", exact: true }).click();
  await expect(viewer).toHaveAttribute("data-measure-points", "0");
});

test("zoom window uses two clicks and Escape cancels in both viewer modes", async ({ page }) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  for (const mode of ["Top-down", "3D fields and heat"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    const viewer = page.getByTestId("coil-iso");
    if (mode !== "Top-down") await expect(viewer).toHaveAttribute("data-camera", /position/);
    const camera = mode === "Top-down" ? null : await viewer.getAttribute("data-camera");
    const button = page.getByRole("button", { name: "Zoom window", exact: true });
    await button.click();
    const picker = page.getByRole("button", { name: "Pick zoom window corners", exact: true });
    const rect = (await picker.boundingBox())!;
    await page.mouse.click(rect.x + rect.width * .3, rect.y + rect.height * .3);
    await expect(picker).toContainText("Choose the opposite corner");
    await page.keyboard.press("Escape");
    await expect(picker).toHaveCount(0); await expect(button).toHaveAttribute("aria-pressed", "false");
    if (camera) await expect(viewer).toHaveAttribute("data-camera", camera);
    await button.click();
    await page.mouse.click(rect.x + rect.width * .3, rect.y + rect.height * .3);
    await page.mouse.click(rect.x + rect.width * .6, rect.y + rect.height * .6);
    await expect(picker).toHaveCount(0); await expect(button).toHaveAttribute("aria-pressed", "false");
    if (camera) {
      const before = JSON.parse(camera);
      await expect.poll(async () => JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(before.zoom);
      const after = JSON.parse((await viewer.getAttribute("data-camera"))!);
      expect(after.target).not.toEqual(before.target);
      const direction = (s: typeof before) => {
        const d = s.position.map((v: number, i: number) => v - s.target[i]);
        const length = Math.hypot(...d); return d.map((v: number) => v / length);
      };
      direction(after).forEach((v: number, i: number) => expect(v).toBeCloseTo(direction(before)[i], 10));
    }
  }
});
