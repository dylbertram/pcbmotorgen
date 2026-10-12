import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test.beforeEach(async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace("export async function bindProjectMenuActions(handlers) {", `export async function bindProjectMenuActions(handlers) {
      const handle = event => handlers[event.detail]?.();
      window.addEventListener('test-file-action', handle);
      return () => window.removeEventListener('test-file-action', handle);`);
    await route.fulfill({ response, body });
  });
});

async function action(page: Page, name: string) {
  await page.evaluate(name => window.dispatchEvent(new CustomEvent("test-file-action", { detail: name })), name);
}
async function settings(page: Page) {
  await action(page, "settings");
  const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

test("appearance saves, persists, and follows system changes in Auto", async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoDesignApp(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  let dialog = await settings(page);
  await page.screenshot({ path: testInfo.outputPath("settings-dark.png") });
  await dialog.getByRole("radio", { name: "Light", exact: true }).check();
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  dialog = await settings(page);
  await expect(dialog.getByRole("radio", { name: "Light", exact: true })).toBeChecked();
  expect(await dialog.evaluate(el => getComputedStyle(el).backgroundColor)).toBe("rgb(248, 250, 252)");
  await page.screenshot({ path: testInfo.outputPath("settings-light.png") });
  await dialog.getByRole("radio", { name: "Auto", exact: true }).check();
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("storage failures leave appearance and current design unchanged", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoDesignApp(page);
  const dialog = await settings(page);
  await dialog.getByRole("radio", { name: "Light", exact: true }).check();
  await dialog.getByLabel("Minimum clearance (mm)").fill("0.3");
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error("Storage unavailable"); }; });
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(dialog.getByRole("alert")).toHaveText(/Could not save settings/);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await settings(page);
  await expect(dialog.getByLabel("Minimum clearance (mm)")).toHaveValue("0.127");
});

test("rule edits are validated, applied, and used by new designs", async ({ page }) => {
  await gotoDesignApp(page);
  let dialog = await settings(page);
  const clearance = dialog.getByLabel("Minimum clearance (mm)");
  await clearance.fill("0");
  await expect(dialog.getByRole("button", { name: "Save settings" })).toBeDisabled();
  await clearance.fill("0.3");
  await dialog.getByLabel("Minimum via drill (mm)").fill("0.4");
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("pcbmotorgen.preferences.v1")!).rules.min_space_mm)).toBe(0.3);
  page.once("dialog", prompt => prompt.accept());
  await action(page, "newProject");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
  dialog = await settings(page);
  await expect(dialog.getByLabel("Minimum clearance (mm)")).toHaveValue("0.3");
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.4");
  await dialog.getByRole("button", { name: "Restore default rules" }).click();
  await expect(dialog.getByLabel("Minimum clearance (mm)")).toHaveValue("0.127");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  dialog = await settings(page);
  await expect(dialog.getByLabel("Minimum clearance (mm)")).toHaveValue("0.3");
});

test("cancel and Escape leave settings unchanged and the modal fits mobile", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoDesignApp(page);
  await page.setViewportSize({ width: 375, height: 640 });
  const dialog = await settings(page);
  await dialog.getByRole("radio", { name: "Light", exact: true }).check();
  await dialog.getByLabel("Minimum clearance (mm)").fill("0.5");
  await expect(dialog.getByRole("button", { name: "Save settings" })).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await page.evaluate(() => localStorage.getItem("pcbmotorgen.preferences.v1"))).toBeNull();
});
