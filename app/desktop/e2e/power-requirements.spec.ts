import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { gotoDesignApp } from "./helpers";
import { declaredLossFixture } from "../src/lib/testFixtures/moveLosses";

async function openPower(page: Page) {
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: "Power requirements", exact: true }).click();
  return page.getByRole("region", { name: "Power requirements", exact: true });
}

test("power tab discloses demo data and downloads a report without fabricated waveforms", async ({ page }) => {
  await gotoDesignApp(page);
  const panel = await openPower(page);
  await expect(panel).toContainText("Demo mode");
  await expect(panel.getByRole("heading", { level: 3 })).toHaveText(["Power demand", "Move and load", "Motor electrical parameters", "Supply and driver"]);
  await expect(panel).not.toContainText(/Scribble|LED|USB|17 faders|60 W|Remaining system decisions/);
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeDisabled();
  await expect(panel.getByRole("button", { name: "Phase electrical CSV", exact: true })).toBeDisabled();
  for (const [button, filename] of [["Download report", "power-requirements-report.md"], ["Requirements CSV", "power-requirements-summary.csv"], ["Model snapshot JSON", "power-requirements-model.json"]]) {
    const downloaded = page.waitForEvent("download");
    await panel.getByRole("button", { name: button, exact: true }).click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe(filename);
    const content = await readFile((await download.path())!, "utf8");
    expect(content).toContain("Unknown");
    expect(content).not.toMatch(/Scribble-strip|LED current|USB-data-only|17 faders|60 W|Remaining system decisions/);
    if (filename.endsWith(".json")) {
      const snapshot = JSON.parse(content);
      expect(snapshot.results_provenance).toBe("demo_results_withheld");
      expect(snapshot.drive).toBeNull();
      expect(snapshot.sweep).toBeNull();
    }
  }
  await page.getByRole("tab", { name: "Magnetic flux density", exact: true }).click();
  await expect(page.locator('[data-dock-panel="flux"]')).toBeVisible();
});

test("move definition requires explicit inputs and demo mode cannot calculate or export a trace", async ({ page }) => {
  await gotoDesignApp(page);
  const panel = await openPower(page);
  await panel.locator("summary").filter({ hasText: "Move definition and calculation" }).click();
  const editor = panel.getByRole("textbox", { name: "Move model JSON", exact: true });
  const template = JSON.parse(await editor.inputValue());
  expect(template.profile.duration_s).toBeNull();
  expect(template.profile.mass_includes).toBe("");
  expect(template.source.accepts_regeneration).toBeNull();
  await editor.fill("{}");
  await panel.getByRole("button", { name: "Apply move definition", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("explicit move and load inputs");
  await expect(panel.getByRole("button", { name: "Calculate move power", exact: true })).toBeDisabled();
  await expect(panel.getByRole("button", { name: "Move time-series CSV", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "Clear move definition", exact: true }).click();
  await expect(panel.getByRole("alert")).toHaveCount(0);
  expect(JSON.parse(await editor.inputValue()).profile.duration_s).toBeNull();
  await panel.getByRole("button", { name: "Add loss-model fields", exact: true }).click();
  const lossTemplate = JSON.parse(await editor.inputValue()).loss_model;
  expect(lossTemplate.basis).toBeNull();
  expect(lossTemplate.ripple.covariance_a2[0]).toEqual([null, null, null]);
  expect(lossTemplate.controller_power_w).toBeNull();
  await panel.getByRole("button", { name: "Clear move definition", exact: true }).click();
});

// These tests inject synthetic DTOs at the transport boundary. They verify
// report state and native save flows, not the Rust solver or native dialogs.
async function syntheticResults(page: Page) {
  await page.route(/\/src\/DocumentEditor\.svelte(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const original = await response.text();
    expect(original).toContain("native: isTauriAvailable()");
    await route.fulfill({ response, body: original.replace("native: isTauriAvailable()", "native: true") });
  });
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      import { mockDriveAnalysis, mockForceSweep } from '/src/lib/ipc/mocks.ts';
      export async function evaluateForceSweep(config) {
        if (window.__failForce) throw new Error('Synthetic force failure');
        return mockForceSweep(config);
      }
      export async function analyzeDrive(config, settings, kf) {
        if (window.__failDrive) throw new Error('Synthetic drive failure');
        if (window.__holdDrive) await new Promise((resolve, reject) => {
          window.__driveWaiting = true;
          window.addEventListener('release-drive', () => reject(new Error('Synthetic drive failure')), {once: true});
        });
        return mockDriveAnalysis(config, settings, kf);
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

test("engineering estimate requires current native inputs and does not overwrite a draft", async ({ page }) => {
  await syntheticResults(page);
  await gotoDesignApp(page);
  const tools = page.getByRole("toolbar", { name: "Design side tools", exact: true });
  await tools.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  const bus = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await bus.fill("12");
  await bus.press("Enter");
  await tools.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  const panel = await openPower(page);
  await expect(panel.getByRole("button", { name: "Phase electrical CSV", exact: true })).toBeEnabled();
  await panel.locator("summary").filter({ hasText: "Move definition and calculation" }).click();
  const editor = panel.getByRole("textbox", { name: "Move model JSON", exact: true });
  const button = panel.getByRole("button", { name: "Add engineering estimate", exact: true });
  await expect(button).toBeEnabled();
  await button.click();
  const draft = JSON.parse(await editor.inputValue());
  expect(draft.loss_model.basis).toBe("engineering_estimate");
  expect(draft.loss_model.omitted_losses.length).toBeGreaterThan(0);
  expect(draft.loss_model.domain.source_voltage_v).toBe(12);
  expect(draft.profile.duration_s).toBeNull();
  expect(draft.source.accepts_regeneration).toBeNull();
  await button.click();
  await expect(panel.getByRole("alert")).toContainText("already has a loss model");
  expect(JSON.parse(await editor.inputValue()).loss_model).toEqual(draft.loss_model);
});

test("native move transport state updates UI and exports, and a cancelled late result cannot reappear", async ({ page }) => {
  await syntheticResults(page);
  // Transport fixtures only. This test does not claim browser physics evidence.
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
        const full = !!window.__declaredLossTransport;
        return { request_id:id, input_sha256:'a'.repeat(64), inputs, provenance:'simulated_not_measured',
          result: { demand: { model_version:'synthetic-ui-transport-test', source_model_scope:full?'declared_loss_model':'partial_declared_scenario', profile:p,
            electrical:{additional_driver_loss_w:full?null:0, loss_model:full?inputs.move_request.loss_model:null, source_accepts_regeneration:true, phase_model:{phase_names:['A','B','C']}},
            feasible:!full, limiting_factors:full?['Required voltage exceeds the physical bus; imposed demand remains available']:[], missing_inputs:[], notes:['Synthetic transport fixture, not numerical evidence.'],
            actual_time_step_s:0.001, requested_distance_m:0.001, sampled_requested_peak_speed_m_s:0.002,
            sampled_requested_positive_acceleration_m_s2:0.01, sampled_requested_negative_acceleration_m_s2:-0.01,
            sampled_phase_peak_a:0.2, phase_rms_a:[0.1,0.1,0.1], copper_energy_j:0.1,
            mechanical_balance_residual_j:0, electrical_balance_residual_j:0,
            source_balance_residual_j:full?1e-10:null, accounted_loss_energy_j:0.9,
            phase_rms_including_declared_ripple_a:full?[0.11,0.11,0.11]:null,
            sampled_phase_peak_including_declared_ripple_a:full?0.22:null,
            loss_energy:full?{winding_dc_ripple_energy_j:0.0001,winding_ac_energy_j:0.01,external_series_energy_j:0.02,
              external_core_energy_j:0.003,switching_energy_j:0.04,deadtime_energy_j:0.005,controller_energy_j:0.02,other_dc_link_energy_j:0.03}:null,
            source:{sampled_positive_peak_power_w:2, sampled_positive_peak_current_a:2/inputs.config.supply_voltage_v, average_power_w:1,
              drawn_energy_j:1.2, returned_energy_j:0.2, net_energy_j:1},
            samples:[{time_s:0,position_m:p.start_m,velocity_m_s:0,acceleration_m_s2:0,motor_force_n:0,
              required_source_voltage_v:inputs.config.supply_voltage_v, required_source_current_a:2/inputs.config.supply_voltage_v, required_source_power_w:2,
              q_current_phase_peak_a:0.2,phase_currents_a:[0.2,-0.1,-0.1], required_phase_voltages_v:[1,-0.5,-0.5],
              required_line_voltage_v:1.5,copper_loss_w:0.1,driver_conduction_loss_w:0.01,mechanical_power_w:0,
              friction_damping_loss_w:0,external_load_power_w:0,kinetic_energy_j:0,magnetic_energy_j:0,
              magnetic_power_w:0,partial_dc_link_power_w:1.99,
              losses:full?{mean_square_phase_current_a2:[0.0401,0.0101,0.0101],phase_peak_envelope_a:[0.22,0.12,0.12],
                winding_dc_ripple_loss_w:0.0001,winding_ac_loss_w:0.01,external_series_loss_w:0.02,external_core_loss_w:0.003,
                switching_loss_w:0.04,deadtime_loss_w:0.005,controller_loss_w:0.02,other_dc_link_loss_w:0.03}:null}] } } };
      }`,
  }));
  await gotoDesignApp(page);
  const panel = await openPower(page);
  await panel.locator("summary").filter({ hasText: "Move definition and calculation" }).click();
  const editor = panel.getByRole("textbox", { name: "Move model JSON", exact: true });
  const request = JSON.parse(await editor.inputValue());
  Object.assign(request, { electrical_angle_at_zero_rad: 0, phase_peak_limit_a: 1, force_positions: 65, additional_driver_loss_w: 0 });
  Object.assign(request.profile, { start_m: 0.0025, end_m: 0.0035, initial_velocity_m_s: 0, final_velocity_m_s: 0,
    duration_s: 1, travel_min_m: 0.0025, travel_max_m: 0.0655, max_speed_m_s: 0.5,
    max_acceleration_m_s2: 2, max_deceleration_m_s2: 2, moving_mass_kg: 0.015,
    mass_includes: "Synthetic UI fixture only", coulomb_friction_n: 0.05, damping_n_s_per_m: 0, external_load_n: 0, time_step_s: 0.001 });
  request.source.accepts_regeneration = true;
  await editor.fill(JSON.stringify(request, null, 2));
  await panel.getByRole("button", { name: "Apply move definition", exact: true }).click();
  const calculate = panel.getByRole("button", { name: "Calculate move power", exact: true });
  await expect(calculate).toBeEnabled();
  await calculate.click();
  const trace = panel.getByRole("button", { name: "Move time-series CSV", exact: true });
  await expect(trace).toBeEnabled();
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Partial scenario peak source power", { exact: true }) })).toContainText("2 W");
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Peak supply power during a move", { exact: true }) })).toContainText("Unknown");
  await trace.click();
  expect(await page.evaluate(() => (window as any).__savedPower.content)).toContain('"required_source_power_W"');
  await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
  const snapshot = JSON.parse(await page.evaluate(() => (window as any).__savedPower.content));
  expect(snapshot.moveResult.result.demand.source.net_energy_j).toBe(1);
  expect(snapshot.moveRequest.profile.mass_includes).toBe("Synthetic UI fixture only");
  await panel.locator("summary").filter({ hasText: "Move definition and calculation" }).click();
  await page.locator('[data-dock-panel="power"]').evaluate(el => { el.scrollTop = 0; });
  await page.screenshot({ path: test.info().outputPath("move-power.png") });
  await panel.locator("summary").filter({ hasText: "Move definition and calculation" }).click();
  request.additional_driver_loss_w = null;
  request.loss_model = declaredLossFixture(snapshot.driveSettings.driver.name, snapshot.driveSettings.driver.rds_on_ohm);
  Object.assign(request.loss_model.domain, { source_voltage_v: snapshot.config.supply_voltage_v,
    pwm_hz: snapshot.driveSettings.pwm_hz, winding_temp_c: snapshot.driveSettings.winding_temp_c });
  await editor.fill(JSON.stringify(request, null, 2));
  await expect(trace).toBeDisabled();
  await page.evaluate(() => { (window as any).__declaredLossTransport = true; });
  await panel.getByRole("button", { name: "Apply move definition", exact: true }).click();
  await calculate.click();
  await expect(trace).toBeEnabled();
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Peak supply power during a move", { exact: true }) })).toContainText("2 W");
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Guaranteed maximum source power", { exact: true }) })).toContainText("Unknown");
  await trace.click();
  const lossTrace = await page.evaluate(() => (window as any).__savedPower.content);
  expect(lossTrace).toContain('"declared_loss_model"');
  expect(lossTrace).toContain('"driver_deadtime_loss_W"');
  await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
  const complete = JSON.parse(await page.evaluate(() => (window as any).__savedPower.content));
  expect(complete.moveResult.result.demand.loss_energy.controller_energy_j).toBe(0.02);
  expect(complete.sections.flatMap((s: any) => s.rows).find((r: any) => r.label === "Electrical energy per move").value).toBe("1 J");
  expect(complete.sections.flatMap((s: any) => s.rows).find((r: any) => r.label === "Physical tracking findings").value).toBe("Imposed demand only");
  await expect(panel.getByText(/Calculated imposed-motion demand remains available/)).toBeVisible();
  request.loss_model.switching.constant_j = 9e-7;
  await editor.fill(JSON.stringify(request, null, 2));
  await expect(trace).toBeDisabled();
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Peak supply power during a move", { exact: true }) })).toContainText("Unknown");
  await panel.getByRole("button", { name: "Apply move definition", exact: true }).click();
  await page.evaluate(() => { (window as any).__holdMove = true; });
  await calculate.click();
  await expect(trace).toBeDisabled();
  await expect.poll(() => page.evaluate(() => (window as any).__moveWaiting)).toBe(true);
  await panel.getByRole("button", { name: "Cancel calculation", exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!(window as any).__cancelledMove)).toBe(true);
  await page.evaluate(() => window.dispatchEvent(new Event("release-move")));
  await expect(trace).toBeDisabled();
  await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
  expect(JSON.parse(await page.evaluate(() => (window as any).__savedPower.content)).moveResult).toBeNull();
});

test("current results export; pending and failed updates never export retained driver values", async ({ page }) => {
  await syntheticResults(page);
  await gotoDesignApp(page);
  const panel = await openPower(page);
  const electrical = panel.getByRole("button", { name: "Phase electrical CSV", exact: true });
  await expect(electrical).toBeEnabled();
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeEnabled();
  await electrical.click();
  await expect(panel.getByRole("status")).toContainText("Saved /exports/power-requirements-electrical.csv");
  expect(await page.evaluate(() => (window as any).__savedPower.content)).toContain('"resistance_hot_ohm"');

  await page.evaluate(() => { (window as any).__holdDrive = true; });
  await page.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12");
  await voltage.press("Enter");
  await page.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  await page.getByRole("tab", { name: "Power requirements", exact: true }).click();
  await expect(electrical).toBeDisabled();
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Winding resistance per phase", { exact: true }) })).toContainText("Unknown");
  await expect.poll(() => page.evaluate(() => (window as any).__driveWaiting)).toBe(true);
  await page.evaluate(() => {
    (window as any).__failDrive = true;
    (window as any).__holdDrive = false;
    window.dispatchEvent(new Event("release-drive"));
  });
  await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
  const snapshot = JSON.parse(await page.evaluate(() => (window as any).__savedPower.content));
  expect(snapshot.config.supply_voltage_v).toBe(12);
  expect(snapshot.drive).toBeNull();
  expect(snapshot.sections.flatMap((section: any) => section.rows).find((row: any) => row.label === "Peak supply power during a move").value).toBe("Unknown");
});

test("failed force updates remove force exports and do not supply an old force constant", async ({ page }) => {
  await syntheticResults(page);
  await gotoDesignApp(page);
  const panel = await openPower(page);
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeEnabled();
  await page.evaluate(() => { (window as any).__failForce = true; });
  await page.getByRole("tab", { name: /^Design/i }).click();
  await page.getByRole("button", { name: "Magnets", exact: true }).click();
  await page.locator("input#magnet-count").fill("6");
  await page.locator("input#magnet-count").press("Enter");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeDisabled();
  await expect(page.getByRole("alert").filter({ hasText: "Computation error: Synthetic force failure" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Phase electrical CSV", exact: true })).toBeEnabled();
  // Sweep completion schedules another driver check. Wait for that check's
  // published snapshot rather than racing its legitimate pending/null state.
  await expect(async () => {
    await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
    const snapshot = JSON.parse(await page.evaluate(() => (window as any).__savedPower.content));
    expect(snapshot.config.magnet_count).toBe(6);
    expect(snapshot.sweep).toBeNull();
    expect(snapshot.drive).not.toBeNull();
    expect(snapshot.drive.thrust_constant_n_per_a).toBeNull();
  }).toPass();

  await page.evaluate(() => { (window as any).__failSave = true; });
  await panel.getByRole("button", { name: "Download report", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Synthetic write failure");
  await page.evaluate(() => { (window as any).__failSave = false; (window as any).__cancelSave = true; });
  await panel.getByRole("button", { name: "Download report", exact: true }).click();
  await expect(panel.getByRole("alert")).toHaveCount(0);
  await expect(panel.getByRole("status")).toHaveCount(0);
});
