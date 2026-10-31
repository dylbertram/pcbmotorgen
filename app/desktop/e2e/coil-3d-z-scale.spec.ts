import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("Z height defaults to 1× and persists across workflow changes", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const dialog = page.getByRole("region", { name: "Coil design workspace", exact: true });
  await dialog.getByRole("button", { name: "Display", exact: true }).click();
  const display = page.getByRole("dialog", { name: "Coil preview display", exact: true });
  await dialog.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await display.getByRole("button", { name: "Close display panel" }).click();
  const viewer = dialog.getByTestId("coil-iso");
  const slider = viewer.getByRole("slider", { name: "Z height scale", exact: true });
  await expect(slider).toHaveAttribute("aria-valuenow", "1");
  await expect(slider).toHaveAttribute("aria-orientation", "vertical");
  await expect(viewer).toHaveAttribute("data-z-scale", "1");
  const canvas = viewer.locator("canvas");
  const before = await canvas.screenshot();

  await slider.focus();
  await page.keyboard.press("ArrowUp");
  await expect(slider).toHaveAttribute("aria-valuenow", "1.1");
  await page.keyboard.press("End");
  await expect(viewer).toHaveAttribute("data-z-scale", "20");
  await expect(viewer.getByLabel("Z height multiplier")).toHaveText("20×");
  await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false);
  await page.keyboard.press("Home");
  await expect(slider).toHaveAttribute("aria-valuenow", "1");

  // Pointer input increases upward, and the slider sits on the left edge.
  const control = viewer.getByRole("group", { name: "Z height", exact: true });
  const track = control.locator('[data-slider-root]');
  const bounds = (await track.boundingBox())!;
  const frame = (await viewer.boundingBox())!;
  expect(bounds.x - frame.x).toBeLessThan(60);
  expect(bounds.height).toBeGreaterThan(bounds.width);
  await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 3);
  await expect.poll(async () => Number(await viewer.getAttribute("data-z-scale"))).toBeGreaterThan(1);
  const value = (await viewer.getAttribute("data-z-scale"))!;
  await page.screenshot({ path: testInfo.outputPath("z-height.png") });

  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const inline = page.getByTestId("coil-iso");
  await expect(inline.getByRole("slider", { name: "Z height scale", exact: true })).toHaveAttribute("aria-valuenow", value);
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(dialog.getByRole("slider", { name: "Z height scale", exact: true })).toHaveAttribute("aria-valuenow", value);
});
