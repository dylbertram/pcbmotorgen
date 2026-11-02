import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp as gotoWorkspace, openDriverChecks, openSimulationView, selectRoutingConnection } from "./helpers";

async function gotoDesignApp(page: Page) {
  await gotoWorkspace(page);
}

async function simulation(page: Page, plot: "driver" | "thrust", settings: "driver" | "drive" | "none" = "none") {
  await openSimulationView(page, "Force");
  if (settings === "driver") {
    const trigger = page.getByRole("button", { name: "Driver settings", exact: true });
    if (await trigger.getAttribute("aria-expanded") !== "true") await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
  } else if (settings === "drive") {
    const trigger = page.getByRole("button", { name: "Drive & force targets", exact: true });
    if (await trigger.getAttribute("aria-expanded") !== "true") await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
  }
  return plot === "driver" ? openDriverChecks(page) : page;
}

test("calculator imports saved drive assumptions without writing its edits back", async ({ page }) => {
  await gotoDesignApp(page);
  const calculator = await simulation(page, "driver", "driver");
  const preview = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const panel = page.getByRole("dialog", { name: "Preview driver settings", exact: true });
  const driverSelector = panel.getByRole("combobox", { name: "Driver to evaluate" });
  await driverSelector.selectOption("DRV8316");
  await expect(panel).toContainText("Adding inductance can reduce PWM current ripple");
  const inductor = preview.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true });
  await expect(inductor).toHaveValue("0");
  await inductor.fill("47");
  await inductor.press("Enter");
  const simulationInductor = calculator.getByRole("spinbutton", { name: "External series inductance per phase (µH)", exact: true });
  await expect(simulationInductor).toHaveValue("0");
  await expect(page.getByLabel("Simulation run controls")).toContainText("Results for the active geometry");
  await calculator.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(simulationInductor).toHaveValue("47");
  const simulationDriver = calculator.getByRole("combobox", { name: "Driver to evaluate" });
  await expect(simulationDriver).toHaveValue("DRV8316");
  await simulationDriver.selectOption("DRV8313");
  await simulationInductor.fill("0");
  await expect(inductor).toHaveValue("47");
  await expect(driverSelector).toHaveValue("DRV8316");
  await expect(preview.getByRole("region", { name: "Preview driver simulation results" })).toHaveCount(0);
  await calculator.close();
});

test("a defined series inductor tames the PWM ripple estimate", async ({ page }) => {
  await gotoDesignApp(page);
  const calculator = await simulation(page, "driver");
  const ripple = calculator.getByRole("row").filter({ hasText: "PWM ripple, peak-to-peak" }).getByRole("cell").first();
  await expect(ripple).not.toHaveText("Not evaluated");
  const initial = Number((await ripple.innerText()).split(" ")[0]);
  const inductor = calculator.getByRole("spinbutton", { name: "External series inductance per phase (µH)", exact: true });
  await inductor.fill("100");
  await inductor.press("Enter");
  await expect.poll(async () => Number((await ripple.innerText()).split(" ")[0])).toBeLessThan(initial);
  await calculator.close();
});

test("voltage updates driver results even when the force sweep fails", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      export async function evaluateForceSweep() { throw new Error('Test sweep failure'); }`,
  }));
  await gotoDesignApp(page);
  const calculator = await simulation(page, "driver", "drive");
  await expect(page.getByRole("alert").filter({ hasText: "Computation error: Test sweep failure" })).toBeVisible();
  const bus = calculator.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await expect(bus).toHaveValue("5");
  await page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true }).fill("12");
  await page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true }).press("Enter");
  await calculator.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(bus).toHaveValue("12");
  await expect(calculator.getByRole("spinbutton", { name: "Force constant, optional (N/A)", exact: true })).toHaveValue("");
  await calculator.close();
});

test("pending or failed source analysis cannot overwrite calculator inputs, and imports recover", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `import * as original from '/src/lib/ipc/physics.ts?original';
      export * from '/src/lib/ipc/physics.ts?original';
      let failed = false;
      const pending = [];
      globalThis.__failPendingDriver = () => {
        failed = true;
        for (const reject of pending.splice(0)) reject(new Error('Test driver failure'));
      };
      export async function analyzeDrive(config, ...args) {
        if (config.supply_voltage_v !== 12) return original.analyzeDrive(config, ...args);
        if (failed) throw new Error('Test driver failure');
        return new Promise((resolve, reject) => { pending.push(reject); });
      }`,
  }));
  await gotoDesignApp(page);
  const calculator = await simulation(page, "driver", "drive");
  const bus = calculator.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await expect(bus).toHaveValue("5");

  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12");
  await voltage.press("Enter");
  await calculator.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(calculator.getByRole("button", { name: "Importing…", exact: true })).toBeDisabled();
  await expect(bus).toHaveValue("5");
  await page.evaluate(() => (window as unknown as { __failPendingDriver: () => void }).__failPendingDriver());
  await expect(calculator.getByRole("alert")).toContainText("No current motor winding analysis");
  await expect(bus).toHaveValue("5");

  await voltage.fill("24");
  await voltage.press("Enter");
  await expect(page.getByLabel("Simulation run controls")).toContainText("Results for the active geometry");
  await calculator.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(bus).toHaveValue("24");
  await expect(calculator.getByRole("alert")).toHaveCount(0);
  await calculator.close();
  expect(pageErrors).toEqual([]);
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
  await simulation(page, "thrust", "drive");
  const plot = page.getByRole("img", { name: "Thrust sweep plot", exact: true });
  await expect(plot.locator("polyline")).toHaveCount(1);
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12"); await voltage.press("Enter");
  await expect(page.getByRole("alert").filter({ hasText: "Computation error: Copper layer is below the first magnetic/conducting stack surface" })).toBeVisible();
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
  await simulation(page, "thrust");
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

test("pending replacement sweeps never send an old Kf with new settings", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `import * as original from '/src/lib/ipc/physics.ts?original';
      export * from '/src/lib/ipc/physics.ts?original';
      let calls = 0;
      export async function evaluateForceSweep(...args) {
        if (calls++ === 0) return original.evaluateForceSweep(...args);
        return new Promise((resolve, reject) => { globalThis.__rejectPendingForce = reject; });
      }
      export async function analyzeDrive(config, settings, kf, cad) {
        globalThis.__pendingDriverInputs ??= [];
        globalThis.__pendingDriverInputs.push({ voltage: config.supply_voltage_v, kf });
        return original.analyzeDrive(config, settings, kf, cad);
      }`,
  }));
  await gotoDesignApp(page);
  await simulation(page, "thrust", "drive");
  await expect.poll(() => page.evaluate(() => (window as any).__pendingDriverInputs?.some((input: any) => input.kf != null))).toBe(true);
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12"); await voltage.press("Enter");
  await expect.poll(() => page.evaluate(() => typeof (window as any).__rejectPendingForce)).toBe("function");
  await expect.poll(() => page.evaluate(() => (window as any).__pendingDriverInputs?.at(-1))).toEqual({ voltage: 12, kf: null });
  expect(await page.evaluate(() => (window as any).__pendingDriverInputs.filter((input: any) => input.voltage === 12 && input.kf != null))).toEqual([]);
  await page.evaluate(() => (window as any).__rejectPendingForce(new Error("Pending replacement rejected")));
  await expect(page.getByRole("alert").filter({ hasText: "Computation error: Pending replacement rejected" })).toBeVisible();
});

test("select drivers and add validated custom parameters in the calculator", async ({ page: workspace }) => {
  await gotoDesignApp(workspace);
  const page = await simulation(workspace, "driver");
  const selector = page.getByRole("combobox", { name: "Driver to evaluate" });
  await selector.selectOption("DRV8316");
  await expect(selector).toHaveValue("DRV8316");
  await page.getByRole("button", { name: "Add driver…", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Add driver", exact: true });
  // Wait for Bits UI's opening autofocus before typing into another field.
  // Otherwise a delayed focus can send the peak-current input into the name.
  await expect(modal.getByLabel("Driver name")).toBeFocused();
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
  await selector.selectOption("DRV8311");
  await selector.selectOption("My driver");
  await expect(selector).toHaveValue("My driver");
  await page.reload();
  await page.getByRole("combobox", { name: "Driver to evaluate" }).selectOption("My driver");
  await expect(page.getByRole("combobox", { name: "Driver to evaluate" })).toHaveValue("My driver");
  await page.close();
});

test("unsupported source topology cannot silently replace a calculator snapshot", async ({ page }) => {
  await gotoDesignApp(page);
  const calculator = await simulation(page, "driver");
  const bus = calculator.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await expect(bus).toHaveValue("5");
  await selectRoutingConnection(page, "delta");
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Coil terminals", exact: true })).toBeVisible();
  await calculator.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(calculator.getByRole("alert")).toContainText("No current motor winding analysis");
  await expect(bus).toHaveValue("5");
  await selectRoutingConnection(page, "star");
  await expect(page.getByLabel("Simulation run controls")).toContainText("Results for the active geometry");
  await calculator.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(calculator.getByRole("alert")).toHaveCount(0);
  await calculator.getByRole("combobox", { name: "Calculator winding connection", exact: true }).selectOption("delta");
  await expect(calculator.getByRole("status")).toContainText("no star substitution");
  await expect(calculator.getByRole("table", { name: "Driver checks", exact: true })).toHaveCount(0);
  await calculator.close();
});
