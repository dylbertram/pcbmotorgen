import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("coil preview driver inductor stays synchronized with simulation", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Expand coil preview", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await preview.getByRole("button", { name: "Driver settings", exact: true }).click();
  const inductor = preview.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true });
  await expect(inductor).toHaveValue("0");
  await inductor.fill("47");
  await inductor.press("Enter");
  await preview.getByRole("button", { name: "Close coil preview", exact: true }).click();

  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const simulationInductor = page.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true });
  await expect(simulationInductor).toHaveValue("47");
  const results = page.locator('section[aria-labelledby="driver-suitability-heading"]');
  await expect(results).toContainText("with 47.0 µH series per phase");
  await simulationInductor.fill("0");
  await simulationInductor.press("Enter");
  await expect(results).not.toContainText("series per phase");

  await page.getByRole("tab", { name: /^Design/i }).click();
  await page.getByRole("button", { name: "Expand coil preview", exact: true }).click();
  await preview.getByRole("button", { name: "Driver settings", exact: true }).click();
  await expect(inductor).toHaveValue("0");
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

test("a rejected new model clears the previous sweep and driver Kf", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `import * as original from '/src/lib/ipc/physics.ts?original';
      export * from '/src/lib/ipc/physics.ts?original';
      let calls = 0;
      export async function evaluateForceSweep(...args) {
        if (calls++ === 0) return original.evaluateForceSweep(...args);
        throw new Error('Copper layer is below the first magnetic/conducting stack surface');
      }
      export async function analyzeDrive(config, settings, kf, cad) {
        globalThis.__placementDriverInputs ??= [];
        globalThis.__placementDriverInputs.push({ voltage: config.supply_voltage_v, kf });
        return original.analyzeDrive(config, settings, kf, cad);
      }`,
  }));
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const plot = page.getByRole("img", { name: "Thrust sweep plot", exact: true });
  await expect(plot.locator("polyline")).toHaveCount(1);
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12"); await voltage.press("Enter");
  await expect(page.getByText("Computation error: Copper layer is below the first magnetic/conducting stack surface")).toBeVisible();
  await expect(plot.locator("polyline")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as unknown as {
    __placementDriverInputs: { voltage: number; kf: number | null }[];
  }).__placementDriverInputs?.at(-1))).toEqual({ voltage: 12, kf: null });
});

test("backplane-only edits invalidate an active simulation, including nested material edits", async ({ page }) => {
  await page.route(/\/src\/lib\/stores\/config\.svelte\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `import * as original from '/src/lib/stores/config.svelte.ts?original';
      export * from '/src/lib/stores/config.svelte.ts?original';
      export class ConfigStore extends original.ConfigStore {
        constructor(...args) { super(...args); globalThis.__activeSimulationConfig = this; }
      }`,
  }));
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `import * as original from '/src/lib/ipc/physics.ts?original';
      export * from '/src/lib/ipc/physics.ts?original';
      export async function evaluateForceSweep(config, ...args) {
        globalThis.__forceBackplaneInputs ??= [];
        globalThis.__forceBackplaneInputs.push(config.backplane == null ? null : JSON.parse(JSON.stringify(config.backplane)));
        return original.evaluateForceSweep(config, ...args);
      }`,
  }));
  await gotoDesignApp(page);
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.getByRole("img", { name: "Thrust sweep plot", exact: true }).locator("polyline")).toHaveCount(1);
  await page.evaluate(() => {
    const state = window as unknown as { __activeSimulationConfig: { backplane: unknown } };
    state.__activeSimulationConfig.backplane = { layers: [{ material: "flex_ferrite", thickness_m: 0.0002 }], housing: null };
  });
  await expect.poll(() => page.evaluate(() => (window as unknown as {
    __forceBackplaneInputs: { layers: { thickness_m: number }[] }[];
  }).__forceBackplaneInputs?.at(-1)?.layers?.[0]?.thickness_m)).toBe(0.0002);
  await page.evaluate(() => {
    const state = window as unknown as { __activeSimulationConfig: { backplane: { layers: { mu_r?: number }[] } } };
    state.__activeSimulationConfig.backplane.layers[0].mu_r = 90;
  });
  await expect.poll(() => page.evaluate(() => (window as unknown as {
    __forceBackplaneInputs: { layers: { mu_r?: number }[] }[];
  }).__forceBackplaneInputs?.at(-1)?.layers?.[0]?.mu_r)).toBe(90);
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
