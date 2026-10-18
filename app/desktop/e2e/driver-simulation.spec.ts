import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("coil preview driver inductor stays synchronized with simulation", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Expand coil preview", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await preview.getByRole("button", { name: "Driver settings", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Preview driver settings", exact: true });
  const driverSelector = panel.getByRole("combobox", { name: "Driver to evaluate" });
  await driverSelector.selectOption("DRV8316");
  await expect(panel).toContainText("Adding inductance can reduce PWM current ripple");
  const previewResults = panel.getByRole("region", { name: "Preview driver simulation results" });
  await expect(previewResults).toContainText("DRV8316");
  const ripple = previewResults.locator("dt", { hasText: "Current ripple, peak-to-peak" }).locator("+ dd");
  const initialRipple = await ripple.textContent();
  const inductor = preview.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true });
  await expect(inductor).toHaveValue("0");
  await inductor.fill("47");
  await inductor.press("Enter");
  await expect(ripple).not.toHaveText(initialRipple!);
  await expect(previewResults).toContainText("Effective phase inductance");
  await expect(previewResults).toContainText("Additional inductance for ripple limit");
  await preview.getByRole("button", { name: "Close coil preview", exact: true }).click();

  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const simulationInductor = page.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true });
  await expect(simulationInductor).toHaveValue("47");
  const simulationDriver = page.getByRole("combobox", { name: "Driver to evaluate" });
  await expect(simulationDriver).toHaveValue("DRV8316");
  await simulationDriver.selectOption("DRV8313");
  const results = page.locator('section[aria-labelledby="driver-suitability-heading"]');
  await expect(results).toContainText("with 47.0 µH series per phase");
  await simulationInductor.fill("0");
  await simulationInductor.press("Enter");
  await expect(results).not.toContainText("series per phase");

  await page.getByRole("tab", { name: /^Design/i }).click();
  await page.getByRole("button", { name: "Expand coil preview", exact: true }).click();
  await preview.getByRole("button", { name: "Driver settings", exact: true }).click();
  await expect(inductor).toHaveValue("0");
  await expect(driverSelector).toHaveValue("DRV8313");
  await expect(previewResults).toContainText("DRV8313");
});

test("a defined series inductor tames the PWM ripple estimate", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const results = page.locator('section[aria-labelledby="driver-suitability-heading"]');
  await expect(results).not.toContainText("series per phase");
  const inductor = page.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true });
  await inductor.fill("100");
  await inductor.press("Enter");
  // The configured inductor feeds the ripple floor and the analysis notes.
  await expect(results).toContainText("with 100 µH series per phase");
});

test("voltage updates driver results even when the force sweep fails", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      export async function evaluateForceSweep() { throw new Error('Test sweep failure'); }`,
  }));
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const results = page.locator('section[aria-labelledby="driver-suitability-heading"]');
  await expect(page.getByText("Computation error: Test sweep failure")).toBeVisible();
  await expect(results).toContainText("at 5.0 V");
  await page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true }).fill("12");
  await page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true }).press("Enter");
  await expect(results).toContainText("at 12.0 V");
  await expect(results).toContainText("10.20 V usable");
});

test("select drivers and add validated custom parameters in a modal", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const selector = page.getByRole("combobox", { name: "Driver to evaluate" });
  await selector.selectOption("DRV8316");
  await expect(selector).toHaveValue("DRV8316");
  await page.getByRole("button", { name: "Add driver…", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Add driver", exact: true });
  await modal.getByLabel("Driver name").fill("My driver");
  await modal.getByLabel("Min supply (V)", { exact: true }).fill("30");
  await modal.getByLabel("Max supply (V)", { exact: true }).fill("24");
  await modal.getByLabel("Peak / OCP (A)").fill("6");
  await modal.getByLabel("Continuous (A RMS)").fill("2");
  await modal.getByLabel("R_DS(on) HS+LS (mΩ)").fill("150");
  await modal.getByLabel("Max PWM (kHz)").fill("200");
  await expect(modal.getByRole("checkbox", { name: /^Built-in delta handling/ })).not.toBeChecked();
  await modal.getByRole("button", { name: "Add driver", exact: true }).click();
  await expect(modal.getByRole("alert")).toContainText("Maximum supply must be greater");
  await modal.getByLabel("Min supply (V)", { exact: true }).fill("3");
  await modal.getByRole("button", { name: "Add driver", exact: true }).click();
  await expect(modal).toBeHidden();
  await expect(selector).toHaveValue("My driver");
  const results = page.locator('section[aria-labelledby="driver-suitability-heading"]');
  await expect(results).toContainText("My driver");
  await selector.selectOption("DRV8311");
  await selector.selectOption("My driver");
  await expect(results).toContainText("My driver");
  await page.reload();
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("combobox", { name: "Driver to evaluate" }).selectOption("My driver");
  await expect(results).toContainText("My driver");
});

test("delta compatibility blocks stale results and returns to the connection control", async ({ page }) => {
  // Supply only the connection contract from motor-coil-generator-add-inputs,
  // without modifying or depending on that checkout's in-progress work.
  await page.route(/\/src\/lib\/ipc\/routing\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/routing.ts?original';
      export async function routingPatternParameters() {
        return [{ key: 'connection', label: 'Winding connection', param_type: 'int', default: 0, min: 0, max: 2 }];
      }`,
  }));
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const results = page.locator('section[aria-labelledby="driver-suitability-heading"]');
  await expect(results).toContainText("at 5.0 V");
  await page.getByRole("tab", { name: /^Design/i }).click();
  const connection = page.getByRole("spinbutton", { name: "Winding connection", exact: true });
  await connection.fill("1");
  await connection.press("Enter");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(results.getByRole("alert")).toContainText("Star (wye) configuration is required");
  await expect(results).not.toContainText("at 5.0 V");
  await results.getByRole("button", { name: "Change winding connection" }).click();
  await expect(page.getByRole("tab", { name: /^Design/i })).toHaveAttribute("aria-selected", "true");
  await connection.fill("2");
  await connection.press("Enter");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(results.getByRole("alert")).toHaveCount(0);
  await expect(results).toContainText("at 5.0 V");
});
