import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

async function selectDesignType(page: Page, name: string) {
  await page.getByRole("button", { name: "Design type", exact: true }).click();
  await page.getByRole("option", { name, exact: true }).click();
}

test("sensor is a design type whose full workflow lives in the Design tab", async ({ page }) => {
  await gotoDesignApp(page);
  await expect(page.locator("#tab-sensor")).toHaveCount(0);
  // Export moved to the native File menu, so it is no longer a workflow tab.
  await expect(page.getByRole("tab", { name: "Export" })).toHaveCount(0);
  await selectDesignType(page, "Sensor");
  await expect(page.getByRole("tab", { name: /^Simulate/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sensor dimensions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Prepare 3D DXF" })).toBeVisible();
  // Sensor IPC intentionally requires Tauri rather than browser mock geometry.
  await expect(page.getByRole("button", { name: "Prepare 3D DXF" })).toBeDisabled();
  await expect(page.locator("#panel-design").getByRole("alert")).toContainText("require the desktop app");
  await page.locator("#sensor-wavelength").fill("48");
  await page.locator("#sensor-wavelength").press("Enter");
  await selectDesignType(page, "Motor coil");
  await expect(page.getByRole("tab", { name: /^Simulate/ })).toBeVisible();
  await selectDesignType(page, "Sensor");
  await expect(page.locator("#sensor-wavelength")).toHaveValue("48");
});

test("switching from motor simulation to sensor opens sensor design", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/ }).click();
  await selectDesignType(page, "Sensor");
  await expect(page.getByRole("tab", { name: /^Design/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#sensor-wavelength")).toBeVisible();
});

test("routing source offers file import last and cancellation keeps the generator", async ({ page }) => {
  await gotoDesignApp(page);
  const source = page.getByRole("button", { name: "Routing source", exact: true });
  const originalSource = await source.textContent();
  await source.click();
  await expect(page.getByRole("option").last()).toHaveText("Load design from file…");
  await page.getByRole("option", { name: "Load design from file…" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(source).toHaveText(originalSource!);
});
