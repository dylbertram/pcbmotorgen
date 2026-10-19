import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("Design is a full-size preview with all settings in the right drawer", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const panel = page.locator("#panel-design");
  await expect(workspace).toBeVisible();
  expect(await workspace.boundingBox()).toEqual(await panel.boundingBox());
  await expect(page.locator("aside[aria-label='Coil preview panel']")).toHaveCount(0);
  const settings = page.getByRole("dialog", { name: "Preview design settings", exact: true });
  await expect(settings).toBeVisible();
  for (const heading of ["design-constraints-heading", "backplane-heading", "topology-board-heading", "magnets-heading"]) {
    await expect(settings.locator(`#${heading}`)).toHaveCount(1);
  }
  const canvas = workspace.locator("canvas[data-segments]");
  await expect.poll(async () => Number(await canvas.getAttribute("data-segments"))).toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath("workspace-settings.png") });
  await settings.getByRole("button", { name: "Close design settings panel" }).click();
  await expect(settings).toHaveCount(0);
  await expect(workspace.getByRole("toolbar", { name: "Preview side tools" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("workspace-canvas.png") });
  await workspace.getByRole("button", { name: "Design settings", exact: true }).click();
  await expect(settings).toBeVisible();
  await settings.getByRole("navigation", { name: "Design settings sections" }).getByRole("button", { name: "Magnets", exact: true }).click();
  const magnetHeading = (await settings.locator("#magnets-heading").boundingBox())!;
  const viewport = (await settings.locator("[data-scroll-area-viewport]").boundingBox())!;
  expect(magnetHeading.y).toBeGreaterThanOrEqual(viewport.y);
  expect(magnetHeading.y + magnetHeading.height).toBeLessThan(viewport.y + viewport.height);
});

test("design edits survive drawer changes and the expanded modal", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  const travel = page.getByRole("spinbutton", { name: "Desired travel (center-to-center)", exact: true });
  await travel.fill("100");
  await travel.press("Enter");
  await page.getByRole("button", { name: "Driver settings", exact: true }).click();
  const driver = page.getByRole("dialog", { name: "Preview driver settings", exact: true });
  await expect(driver.getByRole("combobox", { name: "Driver to evaluate" })).toBeVisible();
  await expect(driver.getByRole("region", { name: "Preview driver simulation results" })).toContainText("Current ripple");
  await page.getByRole("button", { name: "Design settings", exact: true }).click();
  await expect(travel).toHaveValue("100");
  await page.getByRole("button", { name: "Expand coil preview", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await expect(modal.getByRole("spinbutton", { name: "Desired travel (center-to-center)", exact: true })).toHaveValue("100");
  await modal.getByRole("button", { name: "Close coil preview", exact: true }).click();
  await expect(travel).toHaveValue("100");
  await expect(page.locator("#panel-design canvas[data-segments]")).toBeVisible();
});

test("mobile keeps the canvas fixed while the design drawer scrolls", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page);
  const viewport = page.locator("#design-settings-scroll [data-scroll-area-viewport]");
  await expect(viewport).toBeVisible();
  expect(await viewport.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await viewport.evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(page.getByRole("spinbutton", { name: "Magnet count", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(844);
  await page.screenshot({ path: testInfo.outputPath("workspace-mobile.png") });
});
