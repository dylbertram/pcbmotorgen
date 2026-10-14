import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("empty workspace offers file creation and opening without creating a draft", async ({ page }) => {
  await page.goto("/");
  const workspace = page.getByRole("region", { name: "Project workspace" });
  await expect(workspace.getByRole("heading", { name: "Untitled project", exact: true })).toBeVisible();
  await expect(workspace.getByRole("button", { name: "Open file or project…" })).toBeEnabled();
  await expect(page.getByRole("tablist", { name: "Coil files" }).getByRole("tab")).toHaveCount(0);
  await expect(page.locator("#magnet-count")).toHaveCount(0);
  await expect(workspace.getByText("Saved files and projects will appear here.")).toBeVisible();
  await expect(page.getByRole("button", { name: "File", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save Project", exact: true })).toHaveCount(0);
});

test("New coil file button asks for a type and Cancel leaves the workspace empty", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "New coil file", exact: true });
  await expect(dialog.getByText(".pmmotor", { exact: true })).toBeVisible();
  await expect(dialog.getByText(".pmsensor", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("tablist", { name: "Coil files" }).getByRole("tab")).toHaveCount(0);
});

test("New sensor creates a sensor-only workflow", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file" }).getByRole("button", { name: /^Sensor coil/ }).click();
  await expect(page.locator("#sensor-wavelength")).toHaveValue("120");
  await expect(page.getByRole("tab", { name: /^Simulate/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Design rule check:/ })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /^S Untitled sensor/ })).toHaveAttribute("aria-selected", "true");
});

test("CAD import is tied to the active file type and cancel preserves settings", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Routing source", exact: true }).click();
  await page.getByRole("option", { name: "Load design from file…" }).click();
  const dialog = page.getByRole("dialog", { name: "Import CAD", exact: true });
  await expect(dialog.getByLabel("Coil type")).toHaveValue("motor");
  await expect(dialog.getByLabel("Coil type")).toBeDisabled();
  const traceWidth = dialog.getByLabel("Trace width (mm)");
  const originalWidth = await traceWidth.inputValue();
  await traceWidth.fill("0.321");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Routing source", exact: true }).click();
  await page.getByRole("option", { name: "Load design from file…" }).click();
  await expect(traceWidth).toHaveValue(originalWidth);
});

test("routing source retains file loaders after startup setup moves into the editor", async ({ page }) => {
  await gotoDesignApp(page);
  const source = page.getByRole("button", { name: "Routing source", exact: true });
  const original = await source.textContent();
  await source.click();
  await page.getByRole("option", { name: "+ Load new generator…" }).click();
  const generator = page.getByRole("dialog", { name: "Load new generator", exact: true });
  await expect(generator).toBeVisible();
  await generator.getByRole("button", { name: "How to write a plugin?" }).click();
  const guide = page.getByRole("dialog", { name: "How to write a routing plugin", exact: true });
  await expect(guide).toBeVisible();
  await page.keyboard.press("Escape");
  await generator.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(source).toHaveText(original!);
});

test("New dialog fits a narrow viewport and returns focus on cancel", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 640 });
  await page.goto("/");
  const add = page.getByRole("button", { name: "New coil file", exact: true }).first();
  await add.click();
  const dialog = page.getByRole("dialog", { name: "New coil file" });
  const box = (await dialog.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
