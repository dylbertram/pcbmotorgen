import { test, expect } from "@playwright/test";
import { ASIDE, designConstraintsPanel, gotoDesignApp } from "./helpers";

test("design balances the columns and keeps winding details on demand", async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoDesignApp(page);
  const preview = page.locator(ASIDE);
  await expect(preview.locator("#backplane-heading")).toBeVisible();
  await expect(preview.locator("#magnets-heading")).toBeVisible();
  const constraints = designConstraintsPanel(page);
  const diagram = constraints.getByRole("img", { name: "Three-quarter isometric view of the assembly" });
  expect((await diagram.boundingBox())!.height).toBeLessThanOrEqual(150);
  await expect(constraints.getByText("Band margin", { exact: true })).toBeVisible();
  const details = constraints.locator("details");
  await expect(details).not.toHaveAttribute("open", "");
  await details.locator("summary").click();
  await expect(details.getByText("Rest offset", { exact: true })).toBeVisible();
  await details.locator("summary").click();
  await page.screenshot({ path: testInfo.outputPath("design-dark.png"), fullPage: true });
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ path: testInfo.outputPath("design-light.png"), fullPage: true });
});

test("math tooltips render LaTeX with accessible MathML and diagrams", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const constraints = designConstraintsPanel(page);
  await constraints.getByRole("button", { name: "About band margin" }).focus();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toContainText("does not fit");
  await expect(tooltip.locator("math")).toHaveCount(1);
  await expect(tooltip.locator(".katex-error")).toHaveCount(0);
  const image = tooltip.getByRole("img");
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath("math-tooltip.png") });
  await page.keyboard.press("Escape");
  await expect(tooltip).toBeHidden();
});

test("simulation uses the available width and still opens the preview", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.locator(ASIDE)).toBeHidden();
  const diagrams = page.getByRole("region", { name: "Simulation diagrams" });
  expect((await diagrams.boundingBox())!.width).toBeGreaterThan(page.viewportSize()!.width / 2);
  await expect(page.getByText("Performance iteration", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("simulation.png"), fullPage: true });
  await page.getByRole("button", { name: "Open coil preview", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await expect(modal).toBeVisible();
  await modal.getByRole("button", { name: "Close coil preview", exact: true }).click();
});

test.describe("touch layout", () => {
test.use({ hasTouch: true });
test("mobile layout fits the viewport and keeps help reachable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const help = designConstraintsPanel(page).getByRole("button", { name: "About desired travel" });
  await help.scrollIntoViewIfNeeded();
  await help.tap();
  await expect(page.getByRole("tooltip")).toBeVisible();
  const box = (await page.getByRole("tooltip").boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  await page.keyboard.press("Escape");
  await page.screenshot({ path: testInfo.outputPath("mobile.png"), fullPage: true });
});
});

test("driver inductance help explains the circuit without crowding the panel", async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const modal = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await modal.getByRole("button", { name: "Driver settings", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Preview driver settings", exact: true });
  await expect(panel.getByRole("region", { name: "Preview driver simulation results" })).toContainText("Current ripple");
  await panel.getByRole("button", { name: "About series inductance" }).focus();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip.locator("math")).toHaveCount(1);
  await expect(tooltip.getByRole("img")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("driver-help.png") });
});
