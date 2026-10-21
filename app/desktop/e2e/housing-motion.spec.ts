import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

// UI transport fixtures only. Numerical verification uses the Rust model and
// independent diffusion FEM, not these deliberately distinct display values.
async function motionBridge(page: Page) {
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `import * as original from '/src/lib/ipc/physics.ts?original';
      export * from '/src/lib/ipc/physics.ts?original';
      export async function analyzeHousingMotion(config, profile, speed, ...rest) {
        const settings = {housing_motion: profile, target_speed_m_s: speed};
        globalThis.__housingRequests ??= [];
        globalThis.__housingRequests.push(JSON.parse(JSON.stringify({config, settings})));
        const duration = settings.housing_motion.duration_s;
        if (duration === 0.2) {
          await new Promise(resolve => setTimeout(resolve, 700));
          globalThis.__housingDelayedResponseReady = true;
        }
        if (duration === 0.3) throw new Error('Test housing calculation failure');
        const unavailable = config.backplane.housing.material === 'stainless316';
        const power = speed === 0 ? 0 : 5;
        const layerPower = speed === 0 || !config.backplane.layers.length ? 0 : 3;
        const drag = speed === 0 ? 0 : power / Math.abs(speed);
        const housing_motion = unavailable ? { status: 'unavailable', reason: 'Test model applicability failure' } : {
          status: 'experimental', estimate: {
            method: 'ui-fixture-only', housing_material: config.backplane.housing.material,
            speed_m_s: settings.target_speed_m_s, duration_s: duration, equivalent_travel_m: duration * settings.target_speed_m_s,
            housing_drag_n: drag, signed_housing_drag_n: -Math.sign(speed) * drag, housing_joule_power_w: power,
            housing_energy_j: power * duration, layer_joule_power_w: config.backplane.layers.length ? [layerPower] : [], total_stack_joule_power_w: power + layerPower,
            total_stack_drag_n: speed === 0 ? 0 : (power + layerPower) / Math.abs(speed), power_balance_relative_error: 1e-12, quadrature_relative_change: 0.001,
            quadrature_samples: 400, warnings: ['Test model scope warning']
          }
        };
        return housing_motion;
      }`,
  }));
}

async function openHousing(page: Page) {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Stackup", exact: true }).click();
  await page.getByRole("button", { name: "Add backplane", exact: true }).click();
  await page.getByRole("checkbox", { name: "Housing below the backplane", exact: true }).check();
}

test("housing motion is opt-in and separates housing heat from stack heat", async ({ page }) => {
  await motionBridge(page); await openHousing(page);
  const panel = page.getByRole("region", { name: "Experimental housing motion", exact: true });
  await expect(panel.locator("dl")).toHaveCount(0);
  await panel.getByRole("checkbox").check();
  await expect(panel.locator("dl")).toHaveCount(1);
  await expect(panel.locator("dt", { hasText: "Housing Joule heat" }).locator("+ dd")).toHaveText("5.00 W");
  await expect(panel.locator("dt", { hasText: "Total stack Joule heat" }).locator("+ dd")).toHaveText("8.00 W");
  await expect(panel.locator("dt", { hasText: "Housing-equivalent drag" }).locator("+ dd")).toHaveText("10.0 N");
  await expect(panel.locator("dt", { hasText: "Total stack drag" }).locator("+ dd")).toHaveText("16.0 N");
  await expect(panel).toContainText("Test model scope warning");
  await expect.poll(() => page.evaluate(() => (window as any).__housingRequests.at(-1).settings.housing_motion.duration_s)).toBe(0.1);
  await panel.getByRole("checkbox").uncheck();
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("pending or failed housing requests never retain previous numerical results", async ({ page }) => {
  await motionBridge(page); await openHousing(page);
  const panel = page.getByRole("region", { name: "Experimental housing motion", exact: true });
  await panel.getByRole("checkbox").check(); await expect(panel.locator("dl")).toHaveCount(1);
  const duration = panel.getByRole("spinbutton", { name: "Housing steady exposure duration (s)", exact: true });
  await duration.fill("0.2");
  await expect(panel).toContainText("Calculating current housing motion settings");
  await expect(panel.locator("dl")).toHaveCount(0);
  await expect(panel.locator("dt", { hasText: "Housing exposure energy" }).locator("+ dd")).toHaveText("1.00 J");
  await duration.fill("0.3");
  await expect(panel).toContainText("Test housing calculation failure");
  await expect(panel.locator("dl")).toHaveCount(0);
  await duration.fill("0.1"); await expect(panel.locator("dl")).toHaveCount(1);
  await page.getByRole("combobox", { name: "Housing material", exact: true }).selectOption("stainless316");
  await expect(panel).toContainText("Test model applicability failure");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("late housing responses cannot replace a newer failed request", async ({ page }) => {
  await motionBridge(page); await openHousing(page);
  const panel = page.getByRole("region", { name: "Experimental housing motion", exact: true });
  await panel.getByRole("checkbox").check(); await expect(panel.locator("dl")).toHaveCount(1);
  const duration = panel.getByRole("spinbutton", { name: "Housing steady exposure duration (s)", exact: true });
  await duration.fill("0.2");
  await expect.poll(() => page.evaluate(() => (window as any).__housingRequests.at(-1).settings.housing_motion.duration_s)).toBe(0.2);
  await duration.fill("0.3");
  await expect(panel).toContainText("Test housing calculation failure");
  await expect.poll(() => page.evaluate(() => (window as any).__housingDelayedResponseReady)).toBe(true);
  await expect(panel).toContainText("Test housing calculation failure");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("agreed housing and backplane bounds are exposed without magnetic housing choices", async ({ page }) => {
  await openHousing(page);
  const materials = page.getByRole("combobox", { name: "Housing material", exact: true });
  await expect(materials.locator("option")).toHaveText(["Aluminum 6061-T6", "Aluminum 5052-H32", "Stainless 304", "Stainless 316"]);
  await expect(page.getByRole("spinbutton", { name: "Housing wall thickness (mm)", exact: true })).toHaveAttribute("max", "5");
  await expect(page.getByRole("spinbutton", { name: "Housing gap to backplane (mm)", exact: true })).toHaveAttribute("max", "10");
  const add = page.getByRole("button", { name: "Add layer", exact: true });
  await add.click(); await add.click(); await expect(add).toBeDisabled();
  await expect(page.getByRole("spinbutton", { name: "Layer 3 thickness (mm)", exact: true })).toHaveAttribute("max", "2");
});

test("a coreless housing can be analyzed without adding a magnetic shielding layer", async ({ page }) => {
  await motionBridge(page); await gotoDesignApp(page);
  await page.getByRole("button", { name: "Stackup", exact: true }).click();
  await page.getByRole("button", { name: "Add housing only", exact: true }).click();
  await expect(page.getByText("No shielding layer. Housing gap is measured below the PCB.")).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: "Layer 1 thickness (mm)", exact: true })).toHaveCount(0);
  const panel = page.getByRole("region", { name: "Experimental housing motion", exact: true });
  await panel.getByRole("checkbox").check(); await expect(panel.locator("dl")).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => (window as any).__housingRequests.at(-1).config.backplane.layers.length)).toBe(0);
  await expect(panel.locator("dt", { hasText: "Total stack Joule heat" }).locator("+ dd")).toHaveText("5.00 W");
});

test("housing motion does not require a compatible electrical driver or star winding", async ({ page }) => {
  await motionBridge(page); await openHousing(page);
  const panel = page.getByRole("region", { name: "Experimental housing motion", exact: true });
  await panel.getByRole("checkbox").check(); await expect(panel.locator("dl")).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => (window as any).__housingRequests.at(-1).config.routing_params.connection)).toBe(1);
  await expect(panel.getByRole("alert")).toHaveCount(0);
});

test("browser previews do not fabricate housing physics when the desktop backend is absent", async ({ page }) => {
  await openHousing(page);
  const panel = page.getByRole("region", { name: "Experimental housing motion", exact: true });
  await panel.getByRole("checkbox").check();
  await expect(panel).toContainText("Housing motion estimates require the desktop app");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("the current routing selector offers sixteen copper layers but nothing above the program cap", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Routing", exact: true }).click();
  const layers = page.getByLabel("Copper layer count", { exact: true });
  await layers.click();
  await expect(page.getByRole("option", { name: "16", exact: true })).toBeVisible();
  await expect(page.getByRole("option", { name: "18", exact: true })).toHaveCount(0);
  await page.getByRole("option", { name: "16", exact: true }).click();
  await expect(layers).toHaveText("16");
});
