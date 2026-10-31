import { expect, test } from "@playwright/test";
import { gotoDesignApp, openCoilPreview, selectDesignPanel, coilWorkspace } from "./helpers";
import { installViewMenu } from "./view-menu-helpers";

test.beforeEach(async ({ page }) => {
  await installViewMenu(page);
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      import {generateCoils as generate} from '/src/lib/ipc/physics.ts?original';
      export async function generateCoils(config) {
        const result = await generate(config);
        window.orientationGeneration = JSON.parse(JSON.stringify({config, result}));
        return result;
      }`,
  }));
});

test("Routing flips remain generated, compose independently, and persist across views and workflows", async ({ page }, info) => {
  await gotoDesignApp(page);
  await expect.poll(() => page.evaluate(() => !!(window as any).orientationGeneration)).toBe(true);
  const original = await page.evaluate(() => (window as any).orientationGeneration);
  await selectDesignPanel(page, "Routing");
  const panel = page.getByRole("dialog", { name: "Routing", exact: true });
  const labels = ["Mirror left/right (X)", "Mirror up/down (Y)", "Reverse layers (Z)"];
  for (const mask of [1, 3, 7, 6, 4, 5, 2, 0]) {
    for (let axis = 0; axis < 3; axis++) await panel.getByRole("checkbox", { name: labels[axis], exact: true }).setChecked(!!(mask & (1 << axis)));
    const expected = { mirror_x: !!(mask & 1), mirror_y: !!(mask & 2), reverse_layers: !!(mask & 4) };
    await expect.poll(() => page.evaluate(() => (window as any).orientationGeneration.config.routing_orientation)).toEqual(expected);
    const current = await page.evaluate(() => (window as any).orientationGeneration);
    const old = original.result.phases[0];
    const layer = expected.reverse_layers ? original.config.num_layers - 1 - old.layer_idx : old.layer_idx;
    const phase = current.result.phases.find((p: any) => p.layer_idx === layer && p.phase_idx === old.phase_idx);
    expect(phase.segments[0].start[0]).toBeCloseTo(expected.mirror_x ? original.config.active_area_length_m - old.segments[0].start[0] : old.segments[0].start[0], 10);
    expect(phase.segments[0].start[1]).toBeCloseTo(expected.mirror_y ? original.config.board_width_m - old.segments[0].start[1] : old.segments[0].start[1], 10);
    expect(phase.total_length_m).toBe(old.total_length_m);
    await expect(panel.getByRole("group", { name: "Imported CAD pattern", exact: true })).toHaveCount(0);
  }
  await panel.getByRole("checkbox", { name: labels[0], exact: true }).check();
  await panel.getByRole("button", { name: "Close routing panel", exact: true }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: /^Design/i }).click();
  await selectDesignPanel(page, "Routing");
  await expect(panel.getByRole("checkbox", { name: labels[0], exact: true })).toBeChecked();
  await page.screenshot({ path: info.outputPath("routing-orientation-controls.png") });
});

for (const width of [1280, 390]) test(`Star generator keeps flip checkboxes visible at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 844 });
  await gotoDesignApp(page); await selectDesignPanel(page, "Routing");
  const panel = page.getByRole("dialog", { name: "Routing", exact: true });
  await expect(panel.getByRole("button", { name: "Routing source", exact: true })).toContainText("Star (Wye)");
  const orientation = panel.getByRole("group", { name: "Routing orientation", exact: true });
  await expect(orientation.getByRole("checkbox")).toHaveCount(3);
  await expect(orientation.getByRole("button")).toHaveCount(0);
  for (const label of ["Mirror left/right (X)", "Mirror up/down (Y)", "Reverse layers (Z)"]) {
    const checkbox = orientation.getByRole("checkbox", { name: label, exact: true });
    await expect(checkbox).toBeInViewport({ ratio: 1 });
    await expect(checkbox).not.toBeChecked();
    await checkbox.check(); await expect(checkbox).toBeChecked();
  }
  await page.screenshot({ path: info.outputPath(`star-generator-flip-checkboxes-${width}.png`) });
  await expect.poll(() => page.evaluate(() => (window as any).orientationGeneration?.config.routing_orientation))
    .toEqual({ mirror_x: true, mirror_y: true, reverse_layers: true });
  const strands = panel.getByRole("spinbutton", { name: "Strands per period", exact: true });
  await strands.fill("3"); await strands.press("Enter");
  await expect.poll(() => page.evaluate(() => (window as any).orientationGeneration.config.routing_params.num_strands)).toBe(3);
  for (const checkbox of await orientation.getByRole("checkbox").all()) await expect(checkbox).toBeChecked();
  await expect(panel.getByRole("group", { name: "Imported CAD pattern", exact: true })).toHaveCount(0);
});

test("XYZ indicator is camera-aligned, passive and inside every desktop/mobile viewport", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  const workspace = coilWorkspace(page);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const [label, id] of [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]]) {
      await workspace.getByRole("button", { name: label, exact: true }).click();
      const viewer = workspace.getByTestId(`coil-${id}`);
      const axes = viewer.getByRole("img", { name: "Viewport axes: X travel, Y across board, Z up", exact: true });
      await expect(axes).toBeVisible();
      await expect(axes.locator("[data-axis]")).toHaveCount(3);
      await expect(axes).toHaveCSS("pointer-events", "none");
      const box = (await axes.boundingBox())!, frame = (await viewer.boundingBox())!;
      const navigation = (await workspace.getByRole("group", { name: "Zoom controls", exact: true }).boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(frame.x); expect(box.x + box.width).toBeLessThanOrEqual(frame.x + frame.width);
      expect(box.y).toBeGreaterThanOrEqual(frame.y); expect(box.y + box.height).toBeLessThan(navigation.y);
      expect(box.x + box.width).toBeLessThanOrEqual(navigation.x + navigation.width + 1);
      const direction = async (axis: string) => JSON.parse((await axes.locator(`[data-axis="${axis}"]`).getAttribute("data-direction"))!) as number[];
      if (id === "top") { await expect.poll(async () => (await direction("X"))[0]).toBeCloseTo(1); expect((await direction("Y"))[1]).toBeCloseTo(-1); }
      if (id === "front") { await expect.poll(async () => (await direction("Z"))[1]).toBeCloseTo(-1); expect((await direction("X"))[0]).toBeCloseTo(1); }
      if (id === "left") { await expect.poll(async () => (await direction("Y"))[0]).toBeCloseTo(-1); }
      if (id === "iso") {
        const before = await direction("X");
        await page.mouse.move(frame.x + frame.width * .55, frame.y + frame.height * .4); await page.mouse.down();
        await page.mouse.move(frame.x + frame.width * .65, frame.y + frame.height * .5, { steps: 8 }); await page.mouse.up();
        await expect.poll(() => direction("X")).not.toEqual(before);
      }
      await page.screenshot({ path: info.outputPath(`xyz-${id}-${width}.png`) });
    }
  }
});
