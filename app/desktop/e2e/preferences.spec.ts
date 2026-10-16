import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";
import { fileURLToPath } from "node:url";

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

test("driver library edits persist and feed the Simulation selector", async ({ page }) => {
  await gotoDesignApp(page);
  let dialog = await settings(page);

  await dialog.getByRole("button", { name: "Add driver…", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Add driver", exact: true });
  await modal.getByLabel("Driver name").fill("Settings driver");
  await modal.getByLabel("Min supply (V)", { exact: true }).fill("3");
  await modal.getByLabel("Max supply (V)", { exact: true }).fill("30");
  await modal.getByLabel("Peak / OCP (A)").fill("6");
  await modal.getByLabel("Continuous (A RMS)").fill("2");
  await modal.getByLabel("R_DS(on) HS+LS (mΩ)").fill("150");
  await modal.getByLabel("Max PWM (kHz)").fill("200");
  await modal.getByRole("button", { name: "Add driver", exact: true }).click();
  await expect(modal).toBeHidden();
  await expect(dialog.getByText("Settings driver", { exact: true })).toBeVisible();

  await dialog.getByRole("button", { name: "Edit Settings driver", exact: true }).click();
  await dialog.getByLabel("Driver name").fill("Settings driver v2");
  await dialog.getByLabel("Driver maximum supply (V)").fill("48");
  await dialog.getByRole("button", { name: "Save driver", exact: true }).click();
  await expect(dialog.getByText("Settings driver v2", { exact: true })).toBeVisible();
  await expect(dialog.getByText("3–48 V", { exact: false })).toBeVisible();

  // A malformed edit is rejected and leaves the saved value untouched.
  await dialog.getByRole("button", { name: "Edit Settings driver v2", exact: true }).click();
  await dialog.getByLabel("Driver maximum supply (V)").fill("1");
  await dialog.getByRole("button", { name: "Save driver", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Maximum supply must be greater");
  await dialog.getByRole("button", { name: "Cancel driver edit", exact: true }).click();
  await expect(dialog.getByText("3–48 V", { exact: false })).toBeVisible();

  // Persists across reload without saving the project.
  await page.reload();
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
  dialog = await settings(page);
  await expect(dialog.getByText("Settings driver v2", { exact: true })).toBeVisible();

  // The Simulation tab selects from the same library.
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("combobox", { name: "Driver to evaluate" }).selectOption("Settings driver v2");
  await expect(page.locator('section[aria-labelledby="driver-suitability-heading"]')).toContainText("Settings driver v2");
});

test("bundled drivers live in the library, are deletable, and leave the selectors", async ({ page }) => {
  await gotoDesignApp(page);
  let dialog = await settings(page);
  const library = dialog.locator("fieldset", { hasText: "Driver library" });
  for (const name of ["DRV8311", "DRV8316", "DRV8313"]) {
    await expect(library.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(library.getByText("Bundled", { exact: true })).toHaveCount(3);

  await library.getByRole("button", { name: "Remove DRV8313", exact: true }).click();
  await expect(library.getByText("DRV8313", { exact: true })).toHaveCount(0);

  // The Simulation tab reads the same library, so the removed driver is gone.
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const selector = page.getByRole("combobox", { name: "Driver to evaluate" });
  await expect(selector.locator("option", { hasText: "DRV8313" })).toHaveCount(0);
  await expect(selector.locator("option", { hasText: "DRV8316" })).toHaveCount(1);

  // The deletion persists; bundled drivers are not re-seeded on the next load.
  await page.reload();
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
  dialog = await settings(page);
  await expect(dialog.locator("fieldset", { hasText: "Driver library" }).getByText("DRV8313", { exact: true })).toHaveCount(0);
});

test("coil pattern library lists bundled generators and the installed set", async ({ page }) => {
  await gotoDesignApp(page);
  const dialog = await settings(page);
  const library = dialog.locator("fieldset", { hasText: "Coil pattern library" });
  await expect(library).toContainText("Infinity Braid (pcbBraid)");
  await expect(library).toContainText("Built-in");
  await expect(library).toContainText("No user-installed generators.");
  await expect(library.getByRole("button", { name: /^Remove / })).toHaveCount(0);
});

test("KiCad rules import previews supported limits and only applies on save", async ({ page }) => {
  await gotoDesignApp(page);
  let dialog = await settings(page);
  const example = fileURLToPath(new URL("./fixtures/pcbway.kicad_dru", import.meta.url));
  await dialog.getByLabel("Import KiCad DRC rules (.kicad_dru)").setInputFiles(example);
  await expect(dialog.getByRole("status")).toContainText("Imported pcbway.kicad_dru");
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.3");
  await expect(dialog.getByLabel("Minimum via annular ring (mm)")).toHaveValue("0.1");
  await expect(dialog.getByRole("list", { name: "Import limitations" })).toContainText("Skipped conditional");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
  dialog = await settings(page);
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.2");
  await dialog.getByLabel("Import KiCad DRC rules (.kicad_dru)").setInputFiles(example);
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.3");
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  await page.reload();
  dialog = await settings(page);
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.3");
});

test("saved DRC rulesets store, load, and persist across reloads", async ({ page }) => {
  await gotoDesignApp(page);
  let dialog = await settings(page);
  const example = fileURLToPath(new URL("./fixtures/pcbway.kicad_dru", import.meta.url));
  await dialog.getByLabel("Import KiCad DRC rules (.kicad_dru)").setInputFiles(example);
  await dialog.getByLabel("Ruleset name").fill("PCBWay");
  await dialog.getByRole("button", { name: "Save ruleset", exact: true }).click();
  await expect(dialog.getByLabel("Saved rulesets").locator("option", { hasText: "PCBWay" })).toHaveCount(1);

  // Editing a limit and then loading the ruleset restores the saved values.
  await dialog.getByLabel("Minimum via drill (mm)").fill("0.2");
  await dialog.getByLabel("Saved rulesets").selectOption("PCBWay");
  await dialog.getByRole("button", { name: "Load", exact: true }).click();
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.3");
  await dialog.getByRole("button", { name: "Save settings" }).click();

  // The saved ruleset persists on this device, independent of the project.
  await page.reload();
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
  dialog = await settings(page);
  await dialog.getByLabel("Saved rulesets").selectOption("PCBWay");
  await dialog.getByRole("button", { name: "Load", exact: true }).click();
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.3");

  // Deleting clears it from the list and storage.
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog.getByLabel("Saved rulesets")).toHaveCount(0);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("pcbmotorgen.drc_rulesets.v1")!))).toEqual([]);
});

test("invalid rules leave draft limits intact and can be retried", async ({ page }) => {
  await gotoDesignApp(page);
  const dialog = await settings(page);
  await dialog.getByLabel("Minimum clearance (mm)").fill("0.25");
  const upload = dialog.getByLabel("Import KiCad DRC rules (.kicad_dru)");
  await upload.setInputFiles({ name: "invalid.kicad_dru", mimeType: "text/plain", buffer: Buffer.from("(version 1) (rule") });
  await expect(dialog.getByRole("alert")).toContainText("Could not import rules");
  await expect(dialog.getByLabel("Minimum clearance (mm)")).toHaveValue("0.25");
  await upload.setInputFiles({ name: "valid.kicad_dru", mimeType: "text/plain", buffer: Buffer.from('(version 1) (rule "clearance" (constraint clearance (min .2mm)))') });
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.getByLabel("Minimum clearance (mm)")).toHaveValue("0.2");
  await expect(dialog.getByLabel("Minimum via drill (mm)")).toHaveValue("0.2");
});

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
  await action(page, "newProject");
  await page.getByRole("dialog", { name: "Save changes?" }).getByRole("button", { name: "Discard", exact: true }).click();
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
  await action(page, "newFile");
  await page.getByRole("dialog", { name: "New coil file" }).getByRole("button", { name: /^Motor coil/ }).click();
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
