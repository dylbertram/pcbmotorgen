import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel } from "./helpers";
import { readFileSync } from "node:fs";

/** UI fixtures exercise rendering/lifecycle only, not magnetic/thermal validation. */
async function nativeFixture(page: Page) {
  await page.evaluate(async () => {
    const w = window as any;
    const mocks = await import(/* @vite-ignore */ "/src/lib/ipc/mocks.ts");
    const { generatedTerminalGeometry } = await import(/* @vite-ignore */ "/src/lib/generatedTerminalGeometry.ts");
    w.vizCalls = []; w.vizMode = "ready";
    w.__TAURI_INTERNALS__ = { invoke: async (command: string, args: any) => {
      if (command === "generate_coils") return mocks.mockCoils(args.config);
      if (command === "evaluate_force_sweep") return mocks.mockForceSweep(args.config);
      if (command === "compute_height_stack") return mocks.mockHeightStack(args.config);
      if (command === "compute_friction") return mocks.mockFriction(args.config);
      if (command === "travel_envelope") return mocks.mockTravelEnvelope(args.config);
      if (command === "analyze_drive") return mocks.mockDriveAnalysis(args.config, args.drive, null);
      if (command === "sample_b_field") return mocks.mockBFieldGrid(args.config, args.nX, args.nZ, args.xExtentM, args.zExtentM);
      if (command !== "sample_simulation_visualization") throw new Error(`UI fixture has no${command}`);
      w.vizCalls.push(args); const r = args.request, config = args.config;
      const samples = [];
      for (let z = 0; z < r.counts[2]; z++) for (let y = 0; y < r.counts[1]; y++) for (let x = 0; x < r.counts[0]; x++) {
        const p = [x, y, z].map((i, axis) => r.bounds_m[axis][0] + i * (r.bounds_m[axis][1] - r.bounds_m[axis][0]) / (r.counts[axis] - 1));
        const b = [.03 * Math.sin(x), .02 * (y - 2), .08 + .03 * Math.cos(x)];
        samples.push({ position_m: p, b_t: b, magnitude_t: Math.hypot(...b) });
      }
      const geometry = args.cadGeometry ?? generatedTerminalGeometry(mocks.mockCoils(config), config.num_layers, config.pcb_thickness_m * 1000, config.trace_width_m * 1000);
      const edges = geometry.routing.segments.map((s: any, i: number) => {
        const loss = .001 * r.phase_peak_a ** 2 * (1 + i % 5);
        return { net: geometry.coil_phases?.[s.net] ?? s.net, kind: "trace", layers: [s.layer, s.layer],
          points_m: [s.start, s.end].map(p => [p.x * .001, p.y * .001, geometry.layer_z_mm[s.layer] * .001]),
          loss_w: loss, rms_current_a: Math.sqrt(loss), resistance_ohm: 1 };
      });
      const total = edges.reduce((sum: number, edge: any) => sum + edge.loss_w, 0);
      const report = { schema: "simulation-visualization-v1", request_id: r.request_id, input_sha256: "a".repeat(64), implementation_sha256:"b".repeat(64),app_version:"ui-fixture-only",coordinate_convention: "UI fixture XYZ, not numerical evidence",
        field: r.fields ? { method: "analytical-pm-only-xyz", scope: "UI fixture data only", samples,
          magnets: Array.from({ length: config.magnet_count }, (_, i) => ({ center_m: [r.mover_position_m + i * config.magnet_pitch_m, config.board_width_m / 2, config.air_gap_m + config.magnet_height_m / 2],
            size_m: [config.magnet_width_m, config.magnet_cross_width_m, config.magnet_height_m], positive_z: i % 2 === 0 })) } : null,
        heat: r.heat ? { method: "native-resistor-graph-rms-i2r", scope: "UI fixture data only", phase_peak_a: r.phase_peak_a, phase_rms_a: r.phase_peak_a / Math.SQRT2,
          winding_temperature_c: args.driveSettings.winding_temp_c, total_loss_w: total, power_balance_relative_error: 0, edges } : null, heat_unavailable_reason: null };
      w.vizLastReport = report;
      if (w.vizMode === "delayed") return new Promise(resolve => { w.resolveVisualization = () => resolve(report); });
      if (w.vizMode === "failed") throw new Error("Native visualization refused this request");
      return report;
    }};
  });
}

async function show3D(page: Page) {
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("button", { name: "Show 3D fields and heat", exact: true }).click();
  return page.getByTestId("coil-iso");
}

test("3D simulation overlays never fabricate browser fields or heat", async ({ page }) => {
  await gotoDesignApp(page); const viewer = await show3D(page);
  await expect(viewer.getByRole("group", { name: "3D simulation overlays" })).toBeVisible();
  await expect(viewer).toContainText("No browser substitute is shown");
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
  await expect(viewer.getByLabel("Magnetic field legend")).toHaveCount(0);
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(viewer.getByRole("group", { name: "3D simulation overlays" })).toHaveCount(0);
});

test("real WebGL draws both scoped overlays and Z scale never resamples physics", async ({ page }, info) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  await viewer.getByRole("combobox", { name: "3D simulation overlay", exact: true }).selectOption("both");
  await expect(viewer.getByLabel("Copper loss legend")).toContainText("not a temperature");
  await expect(viewer).toHaveAttribute("data-heat-paths", /^[1-9]\d*$/);
  await expect(viewer.getByLabel("Magnetic field legend")).toContainText("No winding or nonlinear material response");
  await viewer.getByRole("combobox", { name: "Field sample density", exact: true }).selectOption("dense");
  await expect(viewer).toHaveAttribute("data-field-samples", "700");
  await viewer.getByLabel("Magnetic field legend").getByText("PM-only model limits", { exact: true }).click();
  await viewer.getByLabel("Copper loss legend").getByText("Loss estimate, not a temperature map", { exact: true }).click();
  await page.screenshot({ path: info.outputPath("ui-fixture-3d-fields-and-loss-true-scale.png") });
  await viewer.getByLabel("Magnetic field legend").getByText("PM-only model limits", { exact: true }).click();
  await viewer.getByLabel("Copper loss legend").getByText("Loss estimate, not a temperature map", { exact: true }).click();
  const calls = await page.evaluate(() => (window as any).vizCalls.length);
  const canvas = viewer.locator("canvas"); const before = await canvas.screenshot();
  await viewer.getByRole("slider", { name: "Z height scale", exact: true }).focus(); await page.keyboard.press("End");
  await expect(viewer).toHaveAttribute("data-z-scale", "20");
  await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false);
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(calls);
  await page.screenshot({ path: info.outputPath("ui-fixture-3d-fields-and-loss.png") });
  await viewer.getByRole("button", { name: "Reset 3D view", exact: true }).click();
  await expect(viewer).toHaveAttribute("data-field-samples", "700");
  await viewer.getByRole("combobox", { name: "3D simulation overlay", exact: true }).selectOption("off");
  await expect(viewer).toHaveAttribute("data-field-samples", "0"); await expect(viewer).toHaveAttribute("data-heat-paths", "0");
});

test("late samples cannot survive tab departure or launch queued work after unmount", async ({ page }) => {
  await gotoDesignApp(page); await nativeFixture(page); await page.evaluate(() => { (window as any).vizMode = "delayed"; });
  const viewer = await show3D(page);
  await expect.poll(() => page.evaluate(() => typeof (window as any).resolveVisualization)).toBe("function");
  await viewer.getByRole("combobox", { name: "Field sample density", exact: true }).selectOption("dense");
  await page.getByRole("tab", { name: /^Design/i }).click();
  const calls = await page.evaluate(() => (window as any).vizCalls.length);
  await page.evaluate(() => { (window as any).resolveVisualization(); });
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(calls);
  await page.evaluate(() => { (window as any).vizMode = "failed"; });
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(viewer).toContainText("Native visualization refused"); await expect(viewer).toHaveAttribute("data-field-samples", "0");
});

test("current edits invalidate old colors and rebind RMS-equivalent I-squared losses", async ({ page }) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await viewer.getByRole("combobox", { name: "3D simulation overlay", exact: true }).selectOption("heat");
  await expect(viewer.getByLabel("Copper loss legend")).toBeVisible();
  const before = await page.evaluate(() => (window as any).vizLastReport.heat.total_loss_w);
  await selectDesignPanel(page, "Drive & force targets");
  await page.getByRole("spinbutton", { name: "Phase current (A)", exact: true }).fill("2");
  await page.getByRole("spinbutton", { name: "Phase current (A)", exact: true }).blur();
  await expect.poll(() => page.evaluate(() => (window as any).vizLastReport.heat?.phase_peak_a)).toBe(2);
  const after = await page.evaluate(() => (window as any).vizLastReport.heat.total_loss_w);
  expect(after / before).toBeCloseTo(4, 8);
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
});

if (process.env.PCB_MOTOR_NATIVE_VISUALIZATION_REPORT) {
  test("actual saved-design Rust data maps to its generated viewer without fitted coordinates", async ({ page }, info) => {
    const native = JSON.parse(readFileSync(process.env.PCB_MOTOR_NATIVE_VISUALIZATION_REPORT!, "utf8"));
    await gotoDesignApp(page);
    const checked = await page.evaluate(async value => {
      const { generatedTerminalGeometry } = await import(/* @vite-ignore */ "/src/lib/generatedTerminalGeometry.ts");
      const { mapCopperLoss } = await import(/* @vite-ignore */ "/src/lib/visualizationGeometry.ts");
      const { validateVisualization } = await import(/* @vite-ignore */ "/src/lib/simulationVisualizationController.ts");
      validateVisualization(value.report, value.request);
      const c = value.config;
      const geometry = value.cad_geometry ?? generatedTerminalGeometry(value.coils, c.num_layers, c.pcb_thickness_m * 1000, c.trace_width_m * 1000);
      const mapping = mapCopperLoss(geometry, value.report.heat);
      return { mapped: mapping.size, edges: value.report.heat.edges.length, total_w: [...mapping.values()].reduce((sum, power) => sum + power, 0),
        reported_w: value.report.heat.total_loss_w, field_samples: value.report.field.samples.length, layer_z_mm: geometry.layer_z_mm };
    }, native);
    expect(checked.mapped).toBeGreaterThan(0); expect(checked.edges).toBeGreaterThan(0);
    expect(checked.total_w).toBeCloseTo(checked.reported_w, 10); expect(checked.field_samples).toBe(240);
    expect(checked.layer_z_mm[0]).toBe(0);
    await info.attach("actual-native-viewer-mapping", { body: JSON.stringify(checked, null, 2), contentType: "application/json" });
  });
}

test("mobile overlays stay inside the viewer and use scrollable explicit legends", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await viewer.getByRole("combobox", { name: "3D simulation overlay", exact: true }).selectOption("both");
  await expect(viewer.getByLabel("Copper loss legend")).toBeVisible();
  const box = (await viewer.boundingBox())!, controls = (await viewer.getByRole("group", { name: "3D simulation overlays" }).boundingBox())!;
  expect(controls.x).toBeGreaterThanOrEqual(box.x); expect(controls.x + controls.width).toBeLessThanOrEqual(box.x + box.width + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("phase visibility filters the heat overlay without recalculating the physical loss", async ({ page }) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await viewer.getByRole("combobox", { name: "3D simulation overlay", exact: true }).selectOption("heat");
  await expect(viewer.getByLabel("Copper loss legend")).toBeVisible();
  const segments = Number(await viewer.getAttribute("data-segments"));
  const legend = await viewer.getByLabel("Copper loss legend").textContent();
  const calls = await page.evaluate(() => (window as any).vizCalls.length);
  await page.getByRole("button", { name: "Layers", exact: true }).click();
  await page.getByRole("checkbox", { name: "Show phase A", exact: true }).uncheck();
  await page.getByRole("button", { name: "Close layers panel", exact: true }).click();
  await expect.poll(async () => Number(await viewer.getAttribute("data-segments"))).toBeLessThan(segments);
  await expect(viewer.getByLabel("Copper loss legend")).not.toHaveText(legend!);
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(calls);
});
