import { test, expect } from "@playwright/test";
import { DESIGN_SCROLL, gotoDesignApp, selectDesignPanel } from "./helpers";

test.describe("Workspace layout geometry", () => {
  test("Design fills the area below the workflow divider", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await gotoDesignApp(page);
    const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
    const nav = (await page.getByRole("navigation", { name: "Design workflows" }).boundingBox())!;
    const bounds = (await workspace.boundingBox())!;
    expect(bounds.x).toBe(0);
    expect(bounds.width).toBe(page.viewportSize()!.width);
    expect(Math.abs(bounds.y - (nav.y + nav.height))).toBeLessThanOrEqual(1);
    const status = (await page.getByRole("group", { name: "Preview status", exact: true }).boundingBox())!;
    expect(Math.abs(bounds.y + bounds.height - status.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(status.y + status.height - page.viewportSize()!.height)).toBeLessThanOrEqual(1);
    const drawing = (await workspace.getByRole("img", { name: "Coil preview", exact: true }).boundingBox())!;
    expect(drawing.width).toBe(bounds.width);
    expect(drawing.height).toBeGreaterThan(300);
  });

  test("settings scroll without moving the canvas or page", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await gotoDesignApp(page);
    const drawing = page.getByRole("img", { name: "Coil preview", exact: true });
    const before = await drawing.boundingBox();
    const viewport = page.locator(`${DESIGN_SCROLL} [data-scroll-area-viewport]`);
    expect(await viewport.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    await viewport.evaluate((el) => { el.scrollTop = el.scrollHeight; });
    expect(await drawing.boundingBox()).toEqual(before);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(page.locator("footer")).toHaveCount(0);
  });

  test("simulation dock scrolls results without moving the workspace", async ({ page }, testInfo) => {
    await gotoDesignApp(page);
    await selectDesignPanel(page, "Routing");
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    const dock = page.getByRole("region", { name: "Simulation results", exact: true });
    await dock.getByRole("tab", { name: "Driver suitability", exact: true }).click();
    const viewport = dock.getByRole("tabpanel", { name: "Driver suitability", exact: true });
    const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
    const drawing = await workspace.boundingBox();
    const width = page.viewportSize()!.width;
    await expect.poll(() => viewport.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    for (const position of [0, 160, Infinity]) {
      await viewport.evaluate((el, position) => { el.scrollTop = Number.isFinite(position) ? position : el.scrollHeight; }, position);
      const bounds = (await viewport.boundingBox())!;
      expect(bounds.x).toBe(0);
      expect(Math.abs(bounds.width - width)).toBeLessThanOrEqual(1);
      expect(await workspace.boundingBox()).toEqual(drawing);
      const status = (await page.getByRole("group", { name: "Preview status", exact: true }).boundingBox())!;
      expect(Math.abs(bounds.y + bounds.height - status.y)).toBeLessThanOrEqual(1);
    }
    await page.screenshot({ path: testInfo.outputPath("simulation-scroll-bottom.png") });
    await viewport.evaluate((el) => { el.scrollTop = 0; });
    await page.screenshot({ path: testInfo.outputPath("simulation-insets.png") });
  });

  test("sensor settings still fill the space below the workflow divider", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await page.goto("/");
    await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
    await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Sensor coil/ }).click();
    const viewport = page.locator("#sensor-settings-scroll [data-scroll-area-viewport]");
    const nav = (await page.getByRole("navigation", { name: "Design workflows" }).boundingBox())!;
    await expect(viewport).toBeVisible();
    expect(await viewport.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    for (const position of [0, 160, Infinity]) {
      await viewport.evaluate((el, position) => { el.scrollTop = Number.isFinite(position) ? position : el.scrollHeight; }, position);
      const bounds = (await viewport.boundingBox())!;
      expect(Math.abs(bounds.y - (nav.y + nav.height))).toBeLessThanOrEqual(1);
      expect(Math.abs(bounds.y + bounds.height - page.viewportSize()!.height)).toBeLessThanOrEqual(1);
    }
  });

  test("switching workflow tabs preserves the selected drawer and simulation scroll", async ({ page }) => {
    await gotoDesignApp(page);
    await selectDesignPanel(page, "Routing");
    await page.getByRole("button", { name: "Display", exact: true }).click();
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    const dock = page.getByRole("region", { name: "Simulation results", exact: true });
    await dock.getByRole("tab", { name: "Driver suitability", exact: true }).click();
    const simulation = dock.getByRole("tabpanel", { name: "Driver suitability", exact: true });
    await expect(simulation.getByRole("heading", { name: "Voltage & speed", exact: true })).toBeVisible();
    await expect.poll(() => simulation.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    // Generation can still replace an initial result with a short pending
    // placeholder. Establish a real scroll offset once content is scrollable.
    let position = 0;
    await expect.poll(async () => {
      position = await simulation.evaluate(el => { el.scrollTop = 200; return el.scrollTop; });
      return position;
    }).toBeGreaterThan(0);
    expect(position).toBeGreaterThan(0);
    await page.getByRole("tab", { name: /^Design/i }).click();
    await expect(page.getByRole("dialog", { name: "Coil preview display", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    await expect(simulation.getByRole("heading", { name: "Voltage & speed", exact: true })).toBeVisible();
    await expect.poll(() => simulation.evaluate((el) => el.scrollTop)).toBe(position);
    await dock.getByRole("button", { name: "Collapse simulation panel", exact: true }).click();
    await dock.getByRole("button", { name: "Expand simulation panel", exact: true }).click();
    await expect.poll(() => simulation.evaluate(el => el.scrollTop)).toBe(position);
    await simulation.evaluate(el => { el.scrollTop = 0; });
    await expect.poll(() => simulation.evaluate(el => el.scrollTop)).toBe(0);
    await page.getByRole("tab", { name: /^Design/i }).click();
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    await expect(simulation.getByRole("heading", { name: "Voltage & speed", exact: true })).toBeVisible();
    await expect.poll(() => simulation.evaluate(el => el.scrollTop)).toBe(0);
  });

  test("settings scrollbar thumb reaches both track ends", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await gotoDesignApp(page);
    await selectDesignPanel(page, "Routing");
    const root = page.locator(DESIGN_SCROLL);
    const viewport = root.locator("[data-scroll-area-viewport]");
    const track = root.locator("[data-scroll-area-scrollbar]");
    const thumb = track.locator("[data-scroll-area-thumb]");
    await expect.poll(() => viewport.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    await root.hover();
    await expect(thumb).toBeVisible();
    for (const end of [false, true]) {
      await viewport.evaluate((el, end) => { el.scrollTop = end ? el.scrollHeight : 0; }, end);
      await expect.poll(async () => {
        const bar = (await track.boundingBox())!;
        const handle = (await thumb.boundingBox())!;
        return end ? Math.abs(handle.y + handle.height - (bar.y + bar.height - 2)) : Math.abs(handle.y - (bar.y + 2));
      }).toBeLessThanOrEqual(1);
    }
  });
});
