import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp as gotoWorkspace } from "./helpers";

async function gotoDesignApp(page: Page) {
  await gotoWorkspace(page);
  await page.getByRole("button", { name: "Stackup", exact: true }).click();
}

// UI fixture only. Numerical agreement is tested against actual solver runs.
const referenceFixture = {
  scope: "periodic static", magnetic_thickness_m: 0.002, mu_initial: 2500,
  saturation_polarization_t: 0.45, elapsed_seconds: 1.5,
  runs: [{ depth_cells: 64, odd_modes: 17, angular_samples: 1024, newton_iterations: 8,
    relative_gradient_residual: 1e-12, field_ratio_at_pm_centre_pcb_top: 1.40534,
    mean_pressure_over_magnet_width_pa: 84665, reflected_normal_modes_t: [],
    quadrature_sampled_peak_b_t: 0.6, quadrature_saturated_fraction: 0.5,
    isolated_sheet_dc_factors_per_alignment: [1.10704656, 1.58252505], differential_relative_residual: 1e-12 }],
  max_field_refinement_change: 0.001, max_pressure_refinement_change: 0.003,
  max_dc_factor_absolute_refinement_change: 0.0002,
  warnings: ["Test material provenance warning"],
};

test("periodic reference never fabricates a browser result", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Add backplane", exact: true }).click();
  await page.getByRole("button", { name: "Run periodic reference", exact: true }).click();
  const panel = page.locator('[aria-label="Periodic static reference"]');
  await expect(panel).toContainText("requires the desktop app");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("periodic reference is explicit, scoped and hidden after settings change", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Add backplane", exact: true }).click();
  const panel = page.locator('[aria-label="Periodic static reference"]');
  await expect(panel.locator("dl")).toHaveCount(0);
  await page.evaluate((fixture) => {
    (window as any).__TAURI_INTERNALS__ = { invoke: async (command: string) => {
      if (command !== "periodic_backplane_reference") throw new Error("test bridge: unexpected command");
      return fixture;
    } };
  }, referenceFixture);
  await panel.getByRole("button", { name: "Run periodic reference", exact: true }).click();
  await expect(panel).toContainText("84.665 kPa");
  await expect(panel).toContainText("1.1070× / 1.5825×");
  await expect(panel).toContainText("not your winding");
  await expect(panel).toContainText("not finite-motor force or a bearing load");
  await page.evaluate(() => { delete (window as any).__TAURI_INTERNALS__; });
  await page.getByRole("spinbutton", { name: "Layer 1 thickness (mm)", exact: true }).fill("1.5");
  await page.getByRole("spinbutton", { name: "Layer 1 thickness (mm)", exact: true }).press("Enter");
  await expect(panel).toContainText("Settings changed");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("late reference completion cannot attach old physics to new settings", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Add backplane", exact: true }).click();
  const panel = page.locator('[aria-label="Periodic static reference"]');
  await page.evaluate(() => {
    (window as any).__TAURI_INTERNALS__ = { invoke: (command: string) => {
      if (command !== "periodic_backplane_reference") throw new Error("unexpected test command");
      return new Promise((resolve) => { (window as any).__resolvePeriodicReference = resolve; });
    } };
  });
  await panel.getByRole("button", { name: "Run periodic reference", exact: true }).click();
  await expect(panel.getByRole("button", { name: "Checking periodic reference…", exact: true })).toBeDisabled();
  await page.evaluate(() => { delete (window as any).__TAURI_INTERNALS__; });
  const thickness = page.getByRole("spinbutton", { name: "Layer 1 thickness (mm)", exact: true });
  await thickness.fill("1.5");
  await thickness.press("Enter");
  await page.evaluate((fixture) => { (window as any).__resolvePeriodicReference(fixture); }, referenceFixture);
  await expect(panel).toContainText("Settings changed");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("a rejected solve shows an error without a preview fallback", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Add backplane", exact: true }).click();
  await page.evaluate(() => {
    (window as any).__TAURI_INTERNALS__ = { invoke: async () => { throw new Error("Reference failed its refinement gate"); } };
  });
  const panel = page.locator('[aria-label="Periodic static reference"]');
  await panel.getByRole("button", { name: "Run periodic reference", exact: true }).click();
  await expect(panel).toContainText("Reference failed its refinement gate");
  await expect(panel.locator("dl")).toHaveCount(0);
});
