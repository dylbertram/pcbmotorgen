import { test, expect } from "@playwright/test";
import { DESIGN_SCROLL, gotoDesignApp } from "./helpers";

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
    expect(Math.abs(bounds.y + bounds.height - page.viewportSize()!.height)).toBeLessThanOrEqual(1);
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

  test("simulation keeps equal side insets and a full-height scroll viewport", async ({ page }, testInfo) => {
    await gotoDesignApp(page);
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    const viewport = page.locator("#simulation-scroll [data-scroll-area-viewport]");
    const nav = (await page.getByRole("navigation", { name: "Design workflows" }).boundingBox())!;
    const diagrams = (await page.getByRole("region", { name: "Simulation diagrams" }).boundingBox())!;
    const settings = (await page.locator("#panel-simulate aside").boundingBox())!;
    const width = page.viewportSize()!.width;
    expect(diagrams.x).toBe(16);
    expect(Math.abs(width - settings.x - settings.width - 16)).toBeLessThanOrEqual(1);
    for (const position of [0, 160, Infinity]) {
      await viewport.evaluate((el, position) => { el.scrollTop = Number.isFinite(position) ? position : el.scrollHeight; }, position);
      const bounds = (await viewport.boundingBox())!;
      expect(bounds.x).toBe(0);
      expect(Math.abs(bounds.width - width)).toBeLessThanOrEqual(1);
      expect(Math.abs(bounds.y - (nav.y + nav.height))).toBeLessThanOrEqual(1);
      expect(Math.abs(bounds.y + bounds.height - page.viewportSize()!.height)).toBeLessThanOrEqual(1);
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
    await page.getByRole("button", { name: "Display", exact: true }).click();
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    const simulation = page.locator("#simulation-scroll [data-scroll-area-viewport]");
    await simulation.evaluate((el) => { el.scrollTop = 200; });
    const position = await simulation.evaluate((el) => el.scrollTop);
    await page.getByRole("tab", { name: /^Design/i }).click();
    await expect(page.getByRole("dialog", { name: "Coil preview display", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    await expect.poll(() => simulation.evaluate((el) => el.scrollTop)).toBe(position);
  });

  test("settings scrollbar thumb reaches both track ends", async ({ page }) => {
    await gotoDesignApp(page);
    const root = page.locator(DESIGN_SCROLL);
    const viewport = root.locator("[data-scroll-area-viewport]");
    const track = root.locator("[data-scroll-area-scrollbar]");
    const thumb = track.locator("[data-scroll-area-thumb]");
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
