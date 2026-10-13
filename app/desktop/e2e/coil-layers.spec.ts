import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("copper width is zoom-independent in world units; centerlines remain thin", async ({ page }) => {
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.stroke;
    CanvasRenderingContext2D.prototype.stroke = function (...args: [Path2D?]) {
      if (this.strokeStyle === "#10b981") {
        this.canvas.dataset.testWorldWidth = String(this.lineWidth);
        this.canvas.dataset.testPixelWidth = String(this.lineWidth * Math.abs(this.getTransform().a));
      }
      if (args[0]) original.call(this, args[0]);
      else original.call(this);
    };
  });
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview — expanded" });
  const canvas = dialog.locator("canvas");
  await expect(canvas).toHaveAttribute("data-trace-mode", "traces");
  await expect(canvas).toHaveAttribute("data-test-world-width", /\d/);
  const width = await canvas.getAttribute("data-test-world-width");
  const pixels = Number(await canvas.getAttribute("data-test-pixel-width"));
  await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(canvas).toHaveAttribute("data-test-world-width", width!);
  await expect.poll(async () => Number(await canvas.getAttribute("data-test-pixel-width"))).toBeGreaterThan(pixels);
  await dialog.getByRole("radio", { name: "Centerlines" }).check();
  await expect(canvas).toHaveAttribute("data-trace-mode", "centerlines");
  const centerlinePixels = Number(await canvas.getAttribute("data-test-pixel-width"));
  await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect.poll(async () => Number(await canvas.getAttribute("data-test-pixel-width"))).toBeCloseTo(centerlinePixels);
});

test("all toggles live in the right-hand Layers panel and survive reopening", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview — expanded" });
  const panel = dialog.getByRole("complementary", { name: "Layers panel" });
  const canvasBox = await dialog.locator("canvas").boundingBox();
  const panelBox = await panel.boundingBox();
  expect(panelBox!.x).toBeGreaterThanOrEqual(canvasBox!.x + canvasBox!.width);
  expect(await panel.getByRole("checkbox").count()).toBe(await dialog.getByRole("checkbox").count());
  await panel.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
  await expect(dialog.locator("canvas")).toHaveAttribute("data-vias", "0");
  await panel.getByRole("radio", { name: "Centerlines" }).check();
  await panel.getByRole("button", { name: "Toggle measure tool" }).click();
  await expect(panel.getByRole("button", { name: "Toggle measure tool" })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await expect(panel.getByRole("checkbox", { name: "Show vias", exact: true })).not.toBeChecked();
  await expect(panel.getByRole("radio", { name: "Centerlines" })).toBeChecked();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel).toBeVisible();
  expect((await dialog.boundingBox())!.width).toBeLessThan(390);
});
