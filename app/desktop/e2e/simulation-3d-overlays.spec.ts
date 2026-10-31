import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel, openCoilPreview } from "./helpers";
import { readFileSync } from "node:fs";

/** UI fixtures exercise rendering/lifecycle only, not magnetic/thermal validation. */
async function nativeFixture(page: Page) {
  await page.evaluate(async () => {
    const w = window as any;
    const mocks = await import(/* @vite-ignore */ "/src/lib/ipc/mocks.ts");
    const { generatedTerminalGeometry } = await import(/* @vite-ignore */ "/src/lib/generatedTerminalGeometry.ts");
    w.vizCalls = []; w.vizMode = "ready";
    w.__TAURI_INTERNALS__ = { invoke: async (command: string, args: any) => {
      if (command === "set_view_menu_state") return;
      if (command === "generate_coils") return mocks.mockCoils(args.config);
      if (command === "evaluate_force_sweep") return mocks.mockForceSweep(args.config);
      if (command === "compute_height_stack") return mocks.mockHeightStack(args.config);
      if (command === "compute_friction") return mocks.mockFriction(args.config);
      if (command === "travel_envelope") return mocks.mockTravelEnvelope(args.config);
      if (command === "analyze_drive") return mocks.mockDriveAnalysis(args.config, args.drive, null);
      if (command === "sample_b_field") return mocks.mockBFieldGrid(args.config, args.nX, args.nZ, args.xExtentM, args.zExtentM);
      if (command === "dc_coupling_capability") return { available: false, reason: "No qualified coil source in this UI fixture." };
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

async function show3D(page: Page, pm = true) {
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await openCoilPreview(page);
  await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  const viewer = page.getByTestId("coil-iso");
  await expect(viewer.getByRole("group", { name: "3D simulation overlays", exact: true })).toBeVisible();
  if (pm) {
    const compact = viewer.getByRole("button", { name: "Field and loss settings", exact: true });
    const narrow = await compact.getAttribute("aria-expanded") === "false";
    if (narrow) await compact.click();
    await viewer.getByRole("combobox", { name: "Magnetic field source", exact: true }).selectOption("pm");
    if (narrow) await compact.click();
  }
  return viewer;
}

test("coil-generated B is primary and never substitutes a PM field for an unqualified design", async ({ page }) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page, false);
  await expect(viewer).toHaveAttribute("data-field-source", "coils");
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
  await expect(viewer).toContainText("No magnet field or wire substitute is shown");
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(0);
});

test("qualified coil controls bind the DC loop, render winding-only data and clear it on current edits", async ({ page }) => {
  await gotoDesignApp(page); await nativeFixture(page);
  await page.evaluate(() => {
    const w=window as any, original=w.__TAURI_INTERNALS__.invoke;
    w.coilStarts=[];
    w.__TAURI_INTERNALS__.invoke=async (command:string,args:any) => {
      if(command==="dc_coupling_capability")return {available:true,winding_field_available:true,qualified_cases:[{case_id:"ui-only",label:"UI-only coil source, not numerical evidence",audit_sha256:"a".repeat(64),declaration:{material_model:{fixture:true},return_geometry:{fixture:true}}}]};
      if(command!=="start_dc_winding_field")return original(command,args);
      w.coilStarts.push(args);
      const s=args.sampling, samples=[];
      for(let z=0;z<s.counts[2];z++)for(let y=0;y<s.counts[1];y++)for(let x=0;x<s.counts[0];x++) {
        const p=[x,y,z].map((v,axis)=>s.bounds_m[axis][0]+v*(s.bounds_m[axis][1]-s.bounds_m[axis][0])/(s.counts[axis]-1));
        const b=[0,0,args.study.current_a*.001];samples.push({position_m:p,b_t:b,magnitude_t:Math.hypot(...b)});
      }
      const field={status:"sampled-qualified-finite-copper-winding-field-only",request_id:args.study.request_id,input_request_sha256:"c".repeat(64),qualified_case:{case_id:"ui-only",label:"UI-only coil source, not numerical evidence",audit_sha256:"a".repeat(64)},sampling:s,loop_current_a:args.study.current_a,
        source_basis_sha256:"b".repeat(64),source_translation_m:[0,0,0],source_elements:1,phase_currents_a:{A:args.study.current_a,C:-args.study.current_a},evidence_hashes:{"ui-fixture-only":"d".repeat(64)},field:{method:"qualified-finite-copper-winding-xyz",scope:"Nonphysical UI fixture only",magnets:[],samples}};
      return {request_id:args.study.request_id,job_id:"ui-coil-job",state:"completed",operation:"winding-field",request_sha256:"c".repeat(64),elapsed_seconds:0,evidence_directory:"ui-only",result:null,error:null,winding_field:field};
    };
  });
  const viewer=await show3D(page,false);
  await viewer.getByRole("combobox",{name:"Audited coil source",exact:true}).selectOption("ui-only");
  await expect(viewer.getByRole("button",{name:"Sample coil B-field",exact:true})).toBeDisabled();
  await viewer.getByRole("checkbox",{name:/I acknowledge this audited placement/}).check();
  await viewer.getByRole("button",{name:"Sample coil B-field",exact:true}).click();
  await expect(viewer).toHaveAttribute("data-field-samples","96");
  const settings = viewer.getByRole("button", { name: "Field and loss settings", exact: true });
  await settings.click(); await expect(settings).toHaveAttribute("aria-expanded", "false");
  await expect(viewer).toHaveAttribute("data-field-samples", "96");
  await settings.click(); await expect(settings).toHaveAttribute("aria-expanded", "true");
  expect(await page.evaluate(() => (window as any).coilStarts.length)).toBe(1);
  await expect(viewer.getByLabel("Magnetic field legend")).toContainText("A: 0.1 A");
  await expect(viewer.getByLabel("Magnetic field legend")).toContainText("C: -0.1 A");
  expect(await page.evaluate(()=>(window as any).vizCalls.length)).toBe(0);
  const starts = await page.evaluate(() => (window as any).coilStarts.length);
  await viewer.getByRole("checkbox", { name: "Show magnets in 3D", exact: true }).uncheck();
  await expect(viewer).toHaveAttribute("data-visible-magnets", "0");
  await expect(viewer).toHaveAttribute("data-field-samples", "96");
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(0);
  await viewer.getByRole("checkbox", { name: "Include magnets in B-field", exact: true }).check();
  await expect(viewer.getByLabel("Magnetic field legend")).toContainText("Coils + magnets, free-space sum");
  await expect(viewer).toHaveAttribute("data-visible-magnets", "0");
  expect(await page.evaluate(() => (window as any).coilStarts.length)).toBe(starts);
  const pmCalls = await page.evaluate(() => (window as any).vizCalls.length);
  await viewer.getByRole("checkbox", { name: "Show magnets in 3D", exact: true }).check();
  await expect(viewer).toHaveAttribute("data-visible-magnets", "12");
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(pmCalls);
  await viewer.getByRole("checkbox", { name: "Include magnets in B-field", exact: true }).uncheck();
  await expect(viewer.getByLabel("Magnetic field legend")).not.toContainText("Coils + magnets");
  await expect(viewer).toHaveAttribute("data-field-samples", "96");
  await viewer.getByText("Qualified coil source and DC drive",{exact:true}).click();
  await viewer.getByRole("combobox",{name:"Coil DC loop current",exact:true}).selectOption("-0.1");
  await expect(viewer).toHaveAttribute("data-field-samples","0");
  expect(await page.evaluate(()=>(window as any).coilStarts.length)).toBe(1);
});

if(process.env.PCB_MOTOR_NATIVE_WINDING_FIELD_REPORT && process.env.PCB_MOTOR_NATIVE_VISUALIZATION_REPORT) {
  test("actual saved-design finite-copper winding field renders without magnet contributions",async ({page},info)=>{
    const winding=JSON.parse(readFileSync(process.env.PCB_MOTOR_NATIVE_WINDING_FIELD_REPORT!,"utf8"));
    const snapshot=JSON.parse(readFileSync(process.env.PCB_MOTOR_NATIVE_VISUALIZATION_REPORT!,"utf8"));
    await gotoDesignApp(page);
    const checked=await page.evaluate(async ({snapshot,winding})=>{
      const {sampledFieldGrid,fieldLineGeometry,fieldSliceGeometry}=await import(/* @vite-ignore */ "/src/lib/simulationFieldGeometry.ts");
      const {generatedTerminalGeometry}=await import(/* @vite-ignore */ "/src/lib/generatedTerminalGeometry.ts");
      const {buildCoilScene}=await import(/* @vite-ignore */ "/src/lib/coilScene.ts");
      const c=snapshot.config,g=snapshot.cad_geometry??generatedTerminalGeometry(snapshot.coils,c.num_layers,c.pcb_thickness_m*1000,c.trace_width_m*1000),scene=buildCoilScene(g);
      sampledFieldGrid(winding.field);
      const lines=fieldLineGeometry(winding.field,scene,1,.5),slice=fieldSliceGeometry(winding.field,scene,1,.5);
      const stats={lineVertices:lines.getAttribute("position").count,sliceVertices:slice.getAttribute("position").count,magnetCount:winding.field.magnets.length,maxB:Math.max(...winding.field.samples.map((s:any)=>s.magnitude_t)),phases:winding.phase_currents_a};
      lines.dispose();slice.dispose();
      const {renderFrozenNativeWindingReport}=await import(/* @vite-ignore */ "/e2e/fixtures/nativeVisualizationHarness.ts");
      (window as any).closeWinding=renderFrozenNativeWindingReport(snapshot,winding);return stats;
    },{snapshot,winding});
    expect(checked.lineVertices).toBeGreaterThan(0);expect(checked.sliceVertices).toBeGreaterThan(0);expect(checked.magnetCount).toBe(0);expect(checked.maxB).toBeGreaterThan(0);
    await expect(page.getByTestId("frozen-native-visualization").locator("canvas")).toBeVisible();
    await page.screenshot({path:info.outputPath("actual-case-a-finite-copper-coil-b-field.png")});
    await info.attach("actual-finite-copper-coil-field-rendering",{body:JSON.stringify(checked,null,2),contentType:"application/json"});
    await page.evaluate(async()=>{await (window as any).closeWinding();});
  });
}

if (process.env.PCB_MOTOR_NATIVE_PAIRED_PM_REPORT && process.env.PCB_MOTOR_NATIVE_WINDING_FIELD_REPORT) {
  test("actual native coil and magnet vectors superpose only on identical physical observations", async ({ page }, info) => {
    const pm = JSON.parse(readFileSync(process.env.PCB_MOTOR_NATIVE_PAIRED_PM_REPORT!, "utf8"));
    const winding = JSON.parse(readFileSync(process.env.PCB_MOTOR_NATIVE_WINDING_FIELD_REPORT!, "utf8"));
    await gotoDesignApp(page);
    const checked = await page.evaluate(async ({ pm, winding }) => {
      const { validateVisualization } = await import(/* @vite-ignore */ "/src/lib/simulationVisualizationController.ts");
      const { combineVisualizationFields } = await import(/* @vite-ignore */ "/src/lib/combineVisualizationFields.ts");
      validateVisualization(pm.report, pm.request);
      const sum = combineVisualizationFields(winding.field, pm.report.field);
      const residual = Math.max(...sum.samples.flatMap((s: any, i: number) => s.b_t.map((v: number, axis: number) => Math.abs(v - winding.field.samples[i].b_t[axis] - pm.report.field.samples[i].b_t[axis]))));
      return { count: sum.samples.length, residual, maxCombined: Math.max(...sum.samples.map((s: any) => s.magnitude_t)), maxCoil: Math.max(...winding.field.samples.map((s: any) => s.magnitude_t)) };
    }, { pm, winding });
    expect(checked.count).toBe(96); expect(checked.residual).toBeLessThan(1e-14); expect(checked.maxCombined).not.toBe(checked.maxCoil);
    await info.attach("actual-native-vector-superposition", { body: JSON.stringify(checked), contentType: "application/json" });
  });
}

test("PM contribution can be disabled while magnet solids remain visible", async ({ page }) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  await viewer.getByRole("checkbox", { name: "Include magnets in B-field", exact: true }).uncheck();
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
  await expect(viewer).toHaveAttribute("data-visible-magnets", "12");
  await expect(viewer).toContainText("No active field source");
  await viewer.getByRole("checkbox", { name: "Show magnets in 3D", exact: true }).uncheck();
  await expect(viewer).toHaveAttribute("data-visible-magnets", "0");
  await viewer.getByRole("checkbox", { name: "Include magnets in B-field", exact: true }).check();
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  await expect(viewer).toHaveAttribute("data-visible-magnets", "0");
});

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
  await expect(viewer).toHaveAttribute("data-field-style", "lines-slice");
  await expect(viewer.getByLabel("Copper loss legend")).toContainText("W/m");
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
  await page.getByRole("button", { name: "Reset view", exact: true }).click();
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
      const { buildCoilScene } = await import(/* @vite-ignore */ "/src/lib/coilScene.ts");
      const { fieldLineGeometry, fieldSliceGeometry } = await import(/* @vite-ignore */ "/src/lib/simulationFieldGeometry.ts");
      validateVisualization(value.report, value.request);
      const c = value.config;
      const geometry = value.cad_geometry ?? generatedTerminalGeometry(value.coils, c.num_layers, c.pcb_thickness_m * 1000, c.trace_width_m * 1000);
      const mapping = mapCopperLoss(geometry, value.report.heat);
      const densities = mapCopperLoss(geometry, value.report.heat, "linear");
      const resistancePerLength: Record<number, number[]> = {};
      for (const edge of value.report.heat.edges) {
        if (edge.kind !== "trace") continue;
        const length = edge.points_m.slice(1).reduce((sum: number, p: number[], i: number) => sum + Math.hypot(...p.map((v, axis) => v - edge.points_m[i][axis])), 0);
        (resistancePerLength[edge.layers[0]] ??= []).push(edge.resistance_ohm / length);
      }
      const perLayerRelativeSpread = Object.values(resistancePerLength).map(values => (Math.max(...values) - Math.min(...values)) / Math.max(...values));
      const scene = buildCoilScene(geometry);
      const lines = fieldLineGeometry(value.report.field, scene, 1, .5), slice = fieldSliceGeometry(value.report.field, scene, 1, .5);
      const lineVertices = lines.getAttribute("position").count, sliceVertices = slice.getAttribute("position").count;
      const finite = [lines, slice].every(g => ["position", "color"].every(name => Array.from(g.getAttribute(name).array).every(Number.isFinite)));
      lines.dispose(); slice.dispose();
      return { mapped: mapping.size, edges: value.report.heat.edges.length, total_w: [...mapping.values()].reduce((sum, power) => sum + power, 0),
        reported_w: value.report.heat.total_loss_w, field_samples: value.report.field.samples.length, layer_z_mm: geometry.layer_z_mm,
        lineVertices, sliceVertices, finite, density_w_per_m: [...densities.values()], perLayerRelativeSpread };
    }, native);
    expect(checked.mapped).toBeGreaterThan(0); expect(checked.edges).toBeGreaterThan(0);
    expect(checked.total_w).toBeCloseTo(checked.reported_w, 10); expect(checked.field_samples).toBe(native.request.counts.reduce((a: number, b: number) => a * b, 1));
    expect(checked.layer_z_mm[0]).toBe(0);
    expect(checked.lineVertices).toBeGreaterThan(0); expect(checked.sliceVertices).toBeGreaterThan(0); expect(checked.finite).toBe(true);
    expect(checked.density_w_per_m.every(v => Number.isFinite(v) && v >= 0)).toBe(true);
    expect(checked.perLayerRelativeSpread.every(v => v < 1e-10)).toBe(true);
    await info.attach("actual-native-viewer-mapping", { body: JSON.stringify(checked, null, 2), contentType: "application/json" });
    await page.evaluate(async value => {
      const { renderFrozenNativeReport } = await import(/* @vite-ignore */ "/e2e/fixtures/nativeVisualizationHarness.ts");
      (window as any).closeNativeReport = renderFrozenNativeReport(value);
    }, native);
    await expect(page.getByTestId("frozen-native-visualization").locator("canvas")).toBeVisible();
    await page.screenshot({ path: info.outputPath("actual-case-a-native-field-lines-and-slice.png") });
    await page.evaluate(async () => { await (window as any).closeNativeReport(); });
  });
}

test("mobile overlays stay inside the viewer and use scrollable explicit legends", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await viewer.getByRole("button", { name: "Field and loss settings", exact: true }).click();
  await viewer.getByRole("combobox", { name: "3D simulation overlay", exact: true }).selectOption("both");
  await viewer.getByRole("button", { name: "Field and loss settings", exact: true }).click();
  await viewer.getByRole("button", { name: "Legends and model limits", exact: true }).click();
  await expect(viewer.getByLabel("Copper loss legend")).toBeVisible();
  await viewer.getByRole("button", { name: "Legends and model limits", exact: true }).click();
  await expect(viewer.getByLabel("Copper loss legend")).toBeHidden();
  const box = (await viewer.boundingBox())!, controls = (await viewer.getByRole("group", { name: "3D simulation overlays" }).boundingBox())!;
  const viewSwitch = (await page.getByRole("group", { name: "Viewport view", exact: true }).boundingBox())!;
  expect(viewSwitch.y).toBeCloseTo(box.y + 8, 0);
  expect(controls.y).toBeGreaterThanOrEqual(viewSwitch.y + viewSwitch.height + 6);
  expect(controls.x).toBeGreaterThanOrEqual(box.x); expect(controls.x + controls.width).toBeLessThanOrEqual(box.x + box.width + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const legend = (await viewer.getByLabel("Simulation overlay legend").boundingBox())!;
  expect(legend.y - (controls.y + controls.height)).toBeGreaterThan(100);
  const axes = (await viewer.getByRole("img", { name: "Viewport axes: X travel, Y across board, Z up", exact: true }).boundingBox())!;
  expect(legend.x + legend.width).toBeLessThanOrEqual(axes.x);
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    await expect(page.locator("html")).toHaveAttribute("data-theme", colorScheme);
    await page.screenshot({ path: info.outputPath(`mobile-field-slice-and-loss-${colorScheme}.png`) });
  }
  await page.evaluate(() => { (window as any).vizMode = "failed"; });
  await viewer.getByRole("button", { name: "Field and loss settings", exact: true }).click();
  await viewer.getByRole("combobox", { name: "Field sample density", exact: true }).selectOption("fine");
  await viewer.getByRole("button", { name: "Field and loss settings", exact: true }).click();
  await expect(viewer.getByRole("status").filter({ hasText: "Native visualization refused" })).toBeVisible();
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
});

test("field style, Y slice and opacity redraw native samples without requesting new physics", async ({ page }, info) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  const calls = await page.evaluate(() => (window as any).vizCalls.length);
  const canvas = viewer.locator("canvas"), initial = await canvas.screenshot();
  await viewer.getByRole("combobox", { name: "Field rendering style", exact: true }).selectOption("slice");
  await expect(viewer).toHaveAttribute("data-field-style", "slice");
  await expect.poll(async () => (await canvas.screenshot()).equals(initial)).toBe(false);
  await viewer.getByRole("slider", { name: "Field slice position", exact: true }).fill("0.25");
  await expect(viewer).toHaveAttribute("data-field-slice", "0.25");
  await viewer.getByRole("combobox", { name: "Field rendering style", exact: true }).selectOption("lines");
  await expect(viewer).toHaveAttribute("data-field-style", "lines");
  await expect(viewer.getByLabel("Magnetic field legend")).toContainText("XZ-projected Bx/Bz");
  await expect(viewer.getByRole("status").filter({ hasText: "3D rendering is unavailable" })).toHaveCount(0);
  await viewer.getByRole("combobox", { name: "Field rendering style", exact: true }).selectOption("lines-3d");
  await expect(viewer).toHaveAttribute("data-field-style", "lines-3d");
  await expect(viewer.getByLabel("Magnetic field legend")).toContainText("3D trajectories");
  await expect(viewer.getByText("Seed plane Y", { exact: true })).toBeVisible();
  await viewer.getByRole("combobox", { name: "Field rendering style", exact: true }).selectOption("arrows");
  await expect(viewer).toHaveAttribute("data-field-style", "arrows");
  await expect(viewer.getByRole("slider", { name: "Field slice position", exact: true })).toHaveCount(0);
  await viewer.getByRole("combobox", { name: "Field rendering style", exact: true }).selectOption("lines-slice");
  await viewer.getByRole("slider", { name: "Field overlay opacity", exact: true }).fill("0.5");
  await viewer.getByRole("button", { name: "XZ field section", exact: true }).click();
  await expect(viewer.getByRole("button", { name: "XZ field section", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(calls);
  await page.screenshot({ path: info.outputPath("ui-fixture-field-lines-and-slice.png") });
});

test("slice lines and direction cues stay coplanar at every slider position without changing native samples", async ({ page }, info) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  const calls = await page.evaluate(() => (window as any).vizCalls.length);
  for (const fraction of [0, .25, .75, 1]) {
    await viewer.getByRole("slider", { name: "Field slice position", exact: true }).fill(String(fraction));
    const checked = await page.evaluate(async fraction => {
      const { fieldLineGeometry, fieldSliceGeometry } = await import(/* @vite-ignore */ "/src/lib/simulationFieldGeometry.ts");
      const field = (window as any).vizLastReport.field, before = JSON.stringify(field);
      const scene = { centerMm: [0, 0, 0], scale: .001 };
      const lines = fieldLineGeometry(field, scene, 1, fraction), slice = fieldSliceGeometry(field, scene, 1, fraction);
      const positions = lines.getAttribute("position"), plane = slice.getAttribute("position").getZ(0);
      let maxDistance = 0;
      for (let i = 0; i < positions.count; i++) maxDistance = Math.max(maxDistance, Math.abs(positions.getZ(i) - plane));
      const ys = field.samples.map((s: any) => s.position_m[1]), y = Math.min(...ys) + fraction * (Math.max(...ys) - Math.min(...ys));
      const result = { vertices: positions.count, maxDistance, unchanged: before === JSON.stringify(field), yMm: y * 1000 };
      lines.dispose(); slice.dispose(); return result;
    }, fraction);
    expect(checked.vertices).toBeGreaterThan(0); expect(checked.maxDistance).toBeLessThan(1e-7); expect(checked.unchanged).toBe(true);
    await expect(viewer.getByLabel("Field slice readout", { exact: true })).toHaveText(`${checked.yMm.toFixed(2)} mm`);
  }
  const toggle = viewer.getByRole("button", { name: "Field and loss settings", exact: true });
  await toggle.click(); await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click(); await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(viewer).toHaveAttribute("data-field-slice", "1");
  expect(await page.evaluate(() => (window as any).vizCalls.length)).toBe(calls);
  await page.screenshot({ path: info.outputPath("projected-field-inspector.png") });
});

test("field inspector aligns inputs and stays clear of the camera and Z rail", async ({ page }, info) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  const panel = viewer.getByRole("group", { name: "3D simulation overlays", exact: true });
  const bounds = (await viewer.boundingBox())!, box = (await panel.boundingBox())!;
  const camera = (await page.getByRole("group", { name: "Zoom controls", exact: true }).boundingBox())!;
  const zRail = (await viewer.getByRole("group", { name: "Z height", exact: true }).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(bounds.x); expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width);
  expect(box.x).toBeGreaterThan(zRail.x + zRail.width);
  expect(box.y + box.height).toBeLessThanOrEqual(camera.y);
  const selects = await panel.getByRole("combobox").all();
  const boxes = await Promise.all(selects.map(select => select.boundingBox()));
  for (const other of boxes.slice(1)) { expect(other!.x).toBeCloseTo(boxes[0]!.x, 0); expect(other!.width).toBeCloseTo(boxes[0]!.width, 0); }
  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await page.screenshot({ path: info.outputPath(`field-inspector-${theme}.png`) });
    await viewer.screenshot({ path: info.outputPath(`field-viewer-${theme}.png`) });
  }
});

test("XZ section changes the actual camera view, not just the selected button", async ({ page }, info) => {
  await gotoDesignApp(page); await nativeFixture(page); const viewer = await show3D(page);
  await expect(viewer).toHaveAttribute("data-field-samples", "240");
  // Isolate the flat PCB and verify the actual camera axis as well as pixels.
  // Physical rectangular copper can be subpixel-thin in an XZ section, so a
  // hue-threshold bounding box can accidentally measure only the via barrels.
  await viewer.getByRole("checkbox", { name: "Include magnets in B-field", exact: true }).uncheck();
  await viewer.getByRole("checkbox", { name: "Show magnets in 3D", exact: true }).uncheck();
  await expect(viewer).toHaveAttribute("data-field-samples", "0");
  const canvas = viewer.locator("canvas");
  // An element screenshot includes HTML controls layered over the canvas.
  // Mask those so slider accents cannot masquerade as copper geometry.
  const masks = [page.getByRole("group", { name: "Zoom controls", exact: true }),
    viewer.getByRole("group", { name: "3D simulation overlays", exact: true }),
    viewer.getByRole("group", { name: "Z height", exact: true }), viewer.getByLabel("Simulation overlay legend")];
  const bitmap = () => canvas.screenshot({ mask: masks, maskColor: "#ffffff" });
  // Settle initial Bounds/camera work before comparing canvas pixels only.
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  const isometric = await bitmap();
  await viewer.getByRole("button", { name: "XZ field section", exact: true }).click();
  await expect(viewer.getByRole("button", { name: "XZ field section", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(async () => (await bitmap()).equals(isometric)).toBe(false);
  await expect.poll(async () => {
    const camera=JSON.parse((await viewer.getAttribute("data-camera"))!);
    const d=camera.position.map((v:number,i:number)=>v-camera.target[i]);
    return Math.abs(d[2])/Math.hypot(...d);
  }).toBeCloseTo(1,10);
  await viewer.screenshot({ path: info.outputPath("projected-xz-section.png") });
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
