import { expect, test, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { gotoDesignApp } from "./helpers";

async function useTwelveVolts(page: Page) {
  const tools = page.getByRole("toolbar", { name: "Design side tools", exact: true });
  await tools.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  const bus = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await bus.fill("12");
  await bus.press("Enter");
  await tools.getByRole("button", { name: "Drive & force targets", exact: true }).click();
}

async function openMove(page: Page) {
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: "Move & power", exact: true }).click();
  return page.getByRole("region", { name: "Move and power", exact: true });
}

test("simulation opens on the move form and keeps demo results out", async ({ page }) => {
  await gotoDesignApp(page);
  const panel = await openMove(page);
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await expect(dock.getByRole("tab")).toHaveText(["Move & power", "Force", "Fields"]);
  await expect(panel.getByRole("spinbutton", { name: "Move start in millimetres", exact: true })).toHaveValue("0");
  const end = panel.getByRole("spinbutton", { name: "Move end in millimetres", exact: true });
  const full = await end.inputValue();
  expect(Number(full)).toBeGreaterThan(0);
  await end.fill("10");
  await panel.getByRole("button", { name: "Full travel", exact: true }).click();
  await expect(end).toHaveValue(full);
  await expect(panel.getByRole("spinbutton", { name: "Move duration in seconds", exact: true })).toHaveValue("0.5");
  await expect(panel).toContainText("magnets only");
  await expect(panel).toContainText("sliding friction");
  await expect(panel).toContainText("Demo mode");
  await expect(panel.getByRole("button", { name: "Calculate power", exact: true })).toBeDisabled();
  await expect(panel.getByRole("button", { name: "Save report", exact: true })).toHaveCount(0);
  await expect(panel.getByRole("textbox", { name: "Move model JSON", exact: true })).toHaveCount(0);
});

async function syntheticMove(page: Page) {
  await page.route(/\/src\/DocumentEditor\.svelte(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const original = await response.text();
    expect(original).toContain("native: isTauriAvailable()");
    await route.fulfill({ response, body: original.replace("native: isTauriAvailable()", "native: true") });
  });
  await page.route(/\/src\/lib\/movePowerJob\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const original = await response.text();
    expect(original).toContain("native: isTauriAvailable");
    await route.fulfill({ response, body: original.replace("native: isTauriAvailable", "native: () => true") });
  });
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      import { mockDriveAnalysis, mockForceSweep } from '/src/lib/ipc/mocks.ts';
      export async function evaluateForceSweep(c) { return mockForceSweep(c); }
      export async function analyzeDrive(c,s,k) { return mockDriveAnalysis(c,s,k); }
      export async function cancelMovePower(id) { window.__cancelledMove = id; return true; }
      export async function evaluateMovePower(id, inputs) {
        if (window.__holdMove) { window.__moveWaiting = true; await new Promise(resolve => window.addEventListener('release-move', resolve, {once:true})); }
        const p = inputs.move_request.profile;
        const estimate = inputs.move_request.loss_model != null;
        const sample = (t, power) => ({ time_s:t, position_m:p.start_m + (p.end_m - p.start_m) * t / p.duration_s,
          velocity_m_s:0.22, acceleration_m_s2:1.4, motor_force_n:0.07,
          required_source_voltage_v:inputs.config.supply_voltage_v, required_source_current_a:power/inputs.config.supply_voltage_v,
          required_source_power_w:power, q_current_phase_peak_a:0.35, phase_currents_a:[0.35,-0.17,-0.17],
          required_phase_voltages_v:[1,-0.5,-0.5], required_line_voltage_v:3, copper_loss_w:0.86,
          driver_conduction_loss_w:0.02, mechanical_power_w:0.015, friction_damping_loss_w:0.011,
          external_load_power_w:0, kinetic_energy_j:0, magnetic_energy_j:0, magnetic_power_w:0,
          partial_dc_link_power_w:0.88, losses:null });
        return { request_id:id, input_sha256:'a'.repeat(64), inputs, provenance:'simulated_not_measured',
          result: { drive: mockDriveAnalysis(inputs.config, inputs.drive, null), full_overlap_bounds_m:[p.travel_min_m,p.travel_max_m],
            conductor_samples:100, force_map_step_m:0.0005, meshing:12,
            demand: { model_version:'synthetic-ui-transport-test', source_model_scope:estimate?'engineering_estimate':'partial_declared_scenario', profile:p,
              electrical:{winding:'balanced_star_sinusoidal', phase_resistance_hot_ohm:4.49, effective_phase_inductance_h:69.25e-6,
                electrical_period_m:0.012, electrical_angle_at_zero_rad:inputs.move_request.electrical_angle_at_zero_rad, force_map:[],
                phase_peak_limit_a:0, source_voltage_v:inputs.config.supply_voltage_v, voltage_headroom:0.85, driver_path_resistance_ohm:0.21,
                additional_driver_loss_w:null, source_accepts_regeneration:true,
                loss_model:estimate?inputs.move_request.loss_model:null, phase_model:{phase_names:['A','B','C'],resistance_hot_ohm:[4.49,4.49,4.49],inductance_h:[[1e-4,0,0],[0,1e-4,0],[0,0,1e-4]],force_map:[]}},
              feasible:true, limiting_factors:[], missing_inputs:estimate?(inputs.move_request.loss_model.omitted_losses||[]).map(s=>'Declared omitted loss: '+s):['Additional switching/dead-time/control loss declaration required for total source demand'],
              actual_time_step_s:p.time_step_s, requested_distance_m:p.end_m-p.start_m,
              sampled_requested_peak_speed_m_s:0.225, sampled_requested_positive_acceleration_m_s2:1.39, sampled_requested_negative_acceleration_m_s2:-1.39,
              achieved_distance_m:null, sampled_phase_peak_a:0.357, phase_rms_a:[0.16,0.19,0.19],
              copper_energy_j:0.22, conduction_energy_j:0.005, mechanical_work_j:0.003, friction_damping_energy_j:0.003,
              external_load_work_j:0, kinetic_energy_change_j:0, magnetic_energy_change_j:0, capacitor_energy_change_j:0,
              mechanical_balance_residual_j:0, electrical_balance_residual_j:0, source_balance_residual_j:estimate?0:null,
              loss_energy:null, accounted_loss_energy_j:0.23,
              phase_rms_including_declared_ripple_a:estimate?[0.17,0.2,0.2]:null,
              sampled_phase_peak_including_declared_ripple_a:estimate?0.464:null,
              source:{sampled_positive_peak_power_w:1.16, sampled_positive_peak_current_a:1.16/inputs.config.supply_voltage_v,
                average_power_w:0.7, drawn_energy_j:0.35, returned_energy_j:0, net_energy_j:0.35},
              notes:['Synthetic transport fixture, not numerical evidence.'],
              samples:[sample(0,1.0), sample(p.duration_s/2,1.16), sample(p.duration_s,1.1)] } } };
      }`,
  }));
  await page.route(/\/src\/lib\/files\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function saveTextToFile(content, fileName, extensions) {
      if (window.__failSave) throw new Error('Synthetic write failure');
      if (window.__cancelSave) return null;
      window.__savedPower = { content, fileName, extensions };
      return '/exports/' + fileName;
    }`,
  }));
}

test("calculate produces a readable estimate, saves an HTML report, and exports data", async ({ page }, testInfo) => {
  await syntheticMove(page);
  await gotoDesignApp(page);
  await useTwelveVolts(page);
  const panel = await openMove(page);
  await panel.getByRole("spinbutton", { name: "Move end in millimetres", exact: true }).fill("60");
  await panel.getByRole("button", { name: "Calculate power", exact: true }).click();
  await expect(panel.getByText("Power for this move", { exact: true })).toBeVisible();
  await expect(panel.getByText("Engineering estimate", { exact: true })).toBeVisible();
  await expect(panel.getByText("Peak supply draw", { exact: true }).locator("..")).toContainText("1.16 W");
  await expect(panel.getByText("Average during the move", { exact: true }).locator("..")).toContainText("700 mW");
  await expect(panel.getByText("Energy per move", { exact: true }).locator("..")).toContainText("350 mJ");
  await expect(panel.getByText("Peak supply current", { exact: true }).locator("..")).toContainText("96.7 mA");
  await expect(panel.getByRole("img", { name: /Power during the move/ })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Calculate power", exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath("move-power-result.png") });
  await expect(panel.getByText(/Backplane and housing/)).toHaveCount(0);

  await panel.getByRole("button", { name: "Save report", exact: true }).click();
  const saved = await page.evaluate(() => (window as any).__savedPower);
  const htmlReport = saved.content as string;
  expect(saved.fileName).toMatch(/-move-report\.html$/);
  expect(saved.content).toContain("1.16 W");
  expect(saved.content).toContain("Engineering estimate");
  expect(saved.content).toContain("Energy per move");
  expect(saved.content).not.toContain("<script>");

  await panel.getByRole("button", { name: "Export data", exact: true }).click();
  await panel.getByRole("button", { name: "Move time series CSV", exact: true }).click();
  const trace = await page.evaluate(() => (window as any).__savedPower);
  expect(trace.content).toContain('"required_source_power_W"');
  await panel.getByRole("button", { name: "Report (Markdown)", exact: true }).click();
  const markdown = await page.evaluate(() => (window as any).__savedPower);
  expect(markdown.fileName).toMatch(/-move-report\.md$/);
  expect(markdown.content).toContain("# ");
  expect(markdown.content).toContain("1.16 W");

  // Editing any move input invalidates the previous result and its report.
  await panel.getByRole("spinbutton", { name: "Move duration in seconds", exact: true }).fill("0.6");
  await expect(panel.getByRole("button", { name: "Save report", exact: true })).toHaveCount(0);
  await expect(panel.getByText("Power for this move", { exact: true })).toHaveCount(0);

  // The saved document is standalone and readable without the app.
  const reportPath = testInfo.outputPath("move-report.html");
  writeFileSync(reportPath, htmlReport);
  await page.goto("file://" + reportPath);
  await expect(page.getByRole("heading", { name: /move power report/i })).toBeVisible();
  await expect(page.getByText("Engineering estimate", { exact: true })).toBeVisible();
  await expect(page.getByText("Energy per move", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("move-report.png"), fullPage: true });
});

test("a cancelled move never publishes a late result", async ({ page }) => {
  await syntheticMove(page);
  await gotoDesignApp(page);
  const panel = await openMove(page);
  await page.evaluate(() => { (window as any).__holdMove = true; });
  await panel.getByRole("button", { name: "Calculate power", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__moveWaiting)).toBe(true);
  await panel.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!(window as any).__cancelledMove)).toBe(true);
  await page.evaluate(() => window.dispatchEvent(new Event("release-move")));
  await expect(panel.getByText("Power for this move", { exact: true })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Save report", exact: true })).toHaveCount(0);
});
