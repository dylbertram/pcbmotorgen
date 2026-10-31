import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp, openCoilPreview, coilWorkspace, selectDesignPanel } from "./helpers";
import { installViewMenu, setViewMenuChecked } from "./view-menu-helpers";

async function revisitWorkspace(page: Page) {
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: /^Design/i }).click();
  await openCoilPreview(page);
}

// Exercise the real dialog, store and preview with a deterministic IPC boundary.
// Parsing and coil assignments themselves are covered by Rust DXF fixtures.
test.beforeEach(async ({ page }) => {
  await installViewMenu(page);
  await page.route(/\/@tauri-apps_plugin-dialog\.js(?:\?.*)?$/, async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace(/async function confirm\(message2, options\) \{[\s\S]*?\n\}/, "async function confirm() { return window.__cadConfirmResult ?? false; }");
    await route.fulfill({ response, body });
  });
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace("export async function bindProjectMenuActions(handlers) {", `export async function bindProjectMenuActions(handlers) {
      window.addEventListener('test-file-action', event => handlers[event.detail]?.());`);
    await route.fulfill({ response, body });
  });
  await page.route(/\/src\/lib\/ipc\/dxf\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    let body = await response.text();
    body = body.replace(/export async function pickCadDxfPath\(\) \{[\s\S]*?\n\}/, `export async function pickCadDxfPath() { return '/fixture/coil-leads.dxf'; }`);
    body = body.replace(/export async function importCadDxf\([\s\S]*?\n\}/, `export async function importCadDxf(path, units, tolerance, width, count, thickness, assignments = {}, preferDetected = false) {
      if (window.__mappingFixture) {
        const segments = ['A', 'B', 'C'].map((net, i) => ({ start: {x:0,y:i*2}, end:{x:2,y:i*2}, layer:0, net, is_active:true }));
        return {warnings:[],geometry:{layer_z_mm:[-1.6,0],trace_width_mm:width,
          source_layer_coils:{L0_A:'A'},
          routing:{format_version:2,segments,curves:[],splines:[],vias:[]}}};
      }
      const source = { L0_A: 'A', L0_B: 'B', holes: 'holes' };
      const source_layer_coils = Object.fromEntries(Object.entries(source).map(([name, coil]) => [name, (assignments[name] ?? coil).trim()]));
      return { warnings: [], units_to_mm: units, source_units_mm: preferDetected ? 25.4 : undefined, geometry: { layer_z_mm: [-1.6, 0], trace_width_mm: width, source_layer_coils,
        routing: { format_version: 2, curves: [], splines: [],
          segments: ['A', 'B'].flatMap((coil, row) => [0, 1].map(x => ({
            start: { x, y: row * 2 }, end: { x: x + 1, y: row * 2 },
            layer: 0, net: source_layer_coils['L0_' + coil], is_active: true,
          }))).concat(window.__cadLayered ? [{ start: { x: 0, y: 0 }, end: { x: 2, y: 0 }, layer: 1, net: source_layer_coils.L0_A, is_active: true }] : []).concat(window.__cadAmbiguous ? [{ start: { x: 1, y: 0 }, end: { x: 1, y: 1 }, layer: 0, net: source_layer_coils.L0_A, is_active: true }] : []),
          vias: window.__cadNoVias ? [] : [{ position: { x: 2, y: 0 }, from_layer: 0, to_layer: 1, net: source_layer_coils.holes }],
        },
      }};
    }`);
    body = body.replace(/export async function editableCoilGeometry\([\s\S]*?\n\}/, "export async function editableCoilGeometry() { return (await importCadDxf('', 1, .05, .4, 2, 1.6)).geometry; }");
    await route.fulfill({ response, body });
  });
});

async function openTerminalTool(page: Page, { layered = false } = {}) {
  await page.addInitScript(({ layered }) => { (window as any).__cadNoVias = !layered; (window as any).__cadLayered = layered; }, { layered });
  const dialog = await openImport(page);
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expectImportCoil(page, "holes", false);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await page.getByRole("toolbar", { name: "Design side tools" }).getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const command = page.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  return { command, tools };
}

test("imported centerlines retain editable trace and via dimensions", async ({ page }) => {
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await selectDesignPanel(page, "Routing");
  for (const [id, value] of [
    ["motor-trace-width", "0.6"],
    ["motor-via-drill", "0.3"],
    ["motor-via-annular-ring", "0.15"],
  ]) {
    const field = page.locator(`#${id}`);
    await expect(field).toBeVisible();
    await expect(field).toBeEnabled();
    await field.fill(value);
    await field.press("Tab");
    await expect(field).toHaveValue(value);
  }
  await expect(page.getByText("Imported paths are active", { exact: false })).toBeVisible();
});

test("inferred ends require one acceptance and never substitute generated copper", async ({ page }) => {
  await page.addInitScript(() => { (window as any).__mappingFixture = true; });
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    let body = await response.text();
    body = body.replace('export async function evaluateForceSweep(config, cadGeometry = null, drive = null) {', `export async function evaluateForceSweep(config, cadGeometry = null, drive = null) {
      window.__mappingSweepCalls = [...(window.__mappingSweepCalls ?? []), cadGeometry];`);
    await route.fulfill({ response, body });
  });
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const notice = page.getByRole("status", { name: "Inferred coil ends" });
  await expect(notice).toBeVisible();
  expect(await page.evaluate(() => (window as any).__mappingSweepCalls ?? [])).toEqual([]);
  await notice.getByRole("button", { name: "Use inferred ends" }).click();
  await expect(notice).toHaveCount(0);
  await expect.poll(async () => page.evaluate(() => (window as any).__mappingSweepCalls?.length ?? 0)).toBeGreaterThan(0);
  expect(await page.evaluate(() => (window as any).__mappingSweepCalls.every((g: any) => Object.keys(g?.coil_terminals ?? {}).length === 3 && g.routing.segments.length === 3))).toBe(true);
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(page.getByRole("heading", { name: "Imported coil phases" })).toHaveCount(0);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(notice).toHaveCount(0);
});

test("review opens coil ends and dismisses the inferred notice without requiring an edit", async ({ page }) => {
  await page.addInitScript(() => { (window as any).__mappingFixture = true; });
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("status", { name: "Inferred coil ends" }).getByRole("button", { name: "Review", exact: true }).click();
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("region", { name: "Set coil terminals", exact: true })).toBeVisible();
  await workspace.getByRole("button", { name: "Close terminals panel" }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.getByRole("status", { name: "Inferred coil ends" })).toHaveCount(0);
});

test("DXF units auto-detect from the file and can be overridden", async ({ page }) => {
  const dialog = await openImport(page);
  const units = dialog.getByLabel("DXF units");
  await expect(units).toHaveValue("auto");
  // Auto reports the header unit the backend detected.
  await expect(dialog.getByTestId("cad-detected-units")).toContainText("detected 25.4 mm/unit");
  // An explicit choice overrides the header and drops the detection note.
  await units.selectOption("1");
  await expect(dialog.getByTestId("cad-detected-units")).toHaveCount(0);
});

test("phase assignment stays in import without conductor-role controls or review checkbox", async ({ page }) => {
  const dialog = await openImport(page);
  await expect(dialog.getByRole("button", { name: /^Mark (active|end-turn)$/ })).toHaveCount(0);
  await dialog.getByRole("combobox", { name: "Phase for coil A" }).selectOption("B");
  await expect(dialog.getByRole("combobox", { name: "Phase for coil A" })).toHaveValue("B");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await expect(page.getByRole("checkbox", { name: "Imported motor mapping reviewed" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Imported coil phases" })).toHaveCount(0);
  await openCoilPreview(page);
  await expect(page.getByRole("button", { name: /^Mark (active|end-turn)$/ })).toHaveCount(0);
});

test("imported geometry renders in the isometric view", async ({ page }) => {
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const modal = coilWorkspace(page);
  await modal.getByRole("button", { name: "Layers", exact: true }).click();
  await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  const iso = modal.getByTestId("coil-iso");
  await expect(iso).toBeVisible();
  await expect(iso).toHaveAttribute("data-layers", /[1-9]/);
  await expect(iso).toHaveAttribute("data-segments", /[1-9]/);
  await expect(iso).toHaveAttribute("data-vias", /[1-9]/);
});

test("terminal defaults are selected automatically, overrides infer the other end, and labels survive simplify", async ({ page }, testInfo) => {
  const { command, tools } = await openTerminalTool(page);
  await expect(command.getByRole("status")).toContainText("Review A");
  await expect(command).toContainText("Driver end");
  await expect(command).toContainText("X 2 mm");
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  const input = page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true });
  await expect(command.getByRole("status")).toContainText("Select the driver end");
  const box = (await input.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.up();
  await expect(command.getByRole("status")).toContainText("Select the driver end");
  await input.click();
  await expect(command.getByRole("status")).toContainText("Review A");
  await expect(command.getByRole("button", { name: "Select neutral end for coil A", exact: true })).toHaveCount(0);
  await expect(command).toContainText("Automatic");
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true }).click();
  await expect(page.getByRole("img", { name: "Coil A Neutral end, L0, X 0 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  await expect(command.getByRole("status")).toContainText("Review A");
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Simplify lines", exact: true })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("coil-terminal-review.png") });
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  const summary = command;
  await expect(summary).toContainText("L0, X 0 mm");
  await expect(summary).toContainText("L0, X 2 mm");
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("L0, X 2 mm");
   await revisitWorkspace(page);
  const terminalToggle = page.getByRole("button", { name: "Set coil terminals", exact: true });
  if (await terminalToggle.getAttribute("aria-expanded") !== "true") await terminalToggle.click();
  await expect(summary).toContainText("L0, X 0 mm");
});

test("terminal drafts support Flip, keeping current points, Cancel, Escape and switching to Measure", async ({ page }) => {
  const { command, tools } = await openTerminalTool(page);
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByRole("img", { name: "Coil A Driver end, L0, X 2 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeEnabled();
  await command.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(command).toHaveCount(0);
  await expect(tools).toBeVisible();
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await tools.getByRole("button", { name: "Toggle measure tool" }).click();
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
});

test("overlapping endpoints are disambiguated by copper layer and support keyboard selection", async ({ page }, testInfo) => {
  const { command } = await openTerminalTool(page, { layered: true });
  await expect(command.getByRole("status")).toContainText("Review A");
  await expect(page.getByRole("img", { name: "Coil A Neutral end, L1, X 0 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  const cards = await coilWorkspace(page).getByRole("group", { name: "IN/OUT direction arrows", exact: true }).locator("rect").evaluateAll((cards) => cards.map((card) => {
    const { x, y, width, height } = card.getBoundingClientRect();
    return { x, y, width, height };
  }));
  expect(cards).toHaveLength(4);
  for (const [i, a] of cards.entries()) for (const b of cards.slice(i + 1)) expect(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("offset-terminal-arrows.png") });
  await expect(command.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveValue("star");
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  const slider = page.getByRole("slider", { name: "Preview layer", exact: true });
  await slider.focus(); await page.keyboard.press("End");
  await expect(page.getByRole("button", { name: /Endpoint coil A, L0/ })).toHaveCount(0);
  const output = page.getByRole("button", { name: "Endpoint coil A, L1, X 0 mm, Y 0 mm", exact: true });
  await output.focus(); await page.keyboard.press("Enter");
  await expect(command.getByRole("status")).toContainText("Review A");
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(command).toContainText("L0, X 0 mm");
  await expect(command).toContainText("L1, X 0 mm");
});

test("ambiguous linked coils require manual picks instead of unsafe defaults", async ({ page }) => {
  await page.addInitScript(() => { (window as any).__cadAmbiguous = true; });
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const command = page.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await expect(command).toContainText("Not selected");
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true }).click();
  await expect(command.getByRole("status")).toContainText("Couldn't identify the opposite end");
  await expect(command.getByRole("button", { name: "Select neutral end for coil A", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(command).toContainText("L0, X 0 mm");
});

test("terminal panel configures multiple phases, switches topology and temporarily replaces motion controls", async ({ page }, testInfo) => {
  const { command } = await openTerminalTool(page);
  const modal = coilWorkspace(page);
  await expect(modal.getByRole("slider", { name: "Preview layer" })).toBeVisible();
  await expect(modal.getByRole("dialog", { name: "Phase waveform", exact: true })).toHaveCount(0);
  await expect(command.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveValue("star");
  await command.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("delta");
  await expect(command).toContainText("next coil's driver end");
  await expect(command).toContainText("Delta end");
  await expect(command.getByRole("button", { name: "Select delta end for coil A", exact: true })).toHaveCount(0);
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await command.getByRole("button", { name: "Select driver end for coil B", exact: true }).click();
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByRole("img", { name: "Coil A Driver end, L0, X 2 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("coil-terminal-defaults-and-flip.png") });
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(modal.getByRole("img", { name: "Coil A Driver end, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close terminals panel" }).click();
  await expect(modal.getByRole("slider", { name: "Preview layer" })).toHaveCount(0);
  // The persistent workspace uses the simulation results dock, not the
  // retired modal's phase-waveform popover.
  await expect(modal.getByRole("dialog", { name: "Phase waveform", exact: true })).toHaveCount(0);
  await expect(modal.getByRole("slider", { name: "Mover position slider (mm)", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Layers", exact: true }).click();
  await setViewMenuChecked(page, "view:terminals", false);
  await expect(modal.getByRole("img", { name: /Coil A Driver end,/ })).toHaveCount(0);
  await setViewMenuChecked(page, "view:terminals", true);
  await revisitWorkspace(page);
  await expect(modal.getByRole("img", { name: "Coil A Driver end, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
});

test("changing a terminal keeps the inspection zoom and offers keyboard-accessible overrides on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { command } = await openTerminalTool(page);
  const modal = coilWorkspace(page);
  await modal.getByRole("group", { name: "Coil preview", exact: true }).dispatchEvent("wheel", { deltaY: -50, ctrlKey: true });
  const zoomControl = modal.getByRole("button", { name: "Reset zoom", exact: true, includeHidden: true });
  const zoom = await zoomControl.textContent();
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await expect(zoomControl).toHaveText(zoom!);
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await command.getByRole("button", { name: "Flip", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeEnabled();
  const tips = await command.locator("[title]").evaluateAll((elements) => elements.map((e) => e.getAttribute("title")!));
  expect(tips.every((tip) => tip.length <= 140)).toBe(true);
});

test("ends that cannot be inferred require manual picks and the notice clears after selection", async ({ page }) => {
  await page.addInitScript(() => { (window as any).__cadNoVias = true; (window as any).__cadAmbiguous = true; });
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const panel = page.locator("#panel-simulate");
  // The phase-mapping box no longer lives in Simulation.
  await expect(panel.getByRole("heading", { name: "Imported coil phases" })).toHaveCount(0);
  // Imported copper with no confirmed ends blocks the simulation and prompts.
  const alert = panel.getByRole("alert").filter({ hasText: "Coil ends could not be inferred" });
  await expect(alert).toBeVisible();
  await expect(panel.getByText("Thrust and driver results use the imported copper.")).toHaveCount(0);

  await alert.getByRole("button", { name: "Select coil ends" }).click();
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  await expect(workspace).toBeVisible();
  const command = page.getByRole("region", { name: "Set coil terminals", exact: true });
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true }).click();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await workspace.getByRole("button", { name: "Close terminals panel" }).click();

  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(alert).toHaveCount(0);
  await expect(panel.getByRole("status", { name: "Inferred coil ends" })).toHaveCount(0);
  const activeResults = panel.locator('[role="tabpanel"]:visible');
  await expect(activeResults).toHaveCount(1);
  await expect(activeResults.getByText("Update the imported geometry before simulating.")).toBeVisible();
  await expect(activeResults.getByText("No imported coil is assigned to phase C.")).toBeVisible();
  await expect(panel.getByText("Thrust and driver results use the imported copper.")).toHaveCount(0);
});

async function openImport(page: Page) {
  await gotoDesignApp(page);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "importCad" })));
  const dialog = page.getByRole("dialog", { name: "Import CAD", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /Choose DXF/ }).click();
  await expect(dialog.getByLabel("Coil for source layer L0_A")).toHaveValue("A");
  await expect(page.getByRole("button", { name: "Layers", exact: true })).toHaveCount(1);
  return dialog;
}

async function expectImportCoil(page: Page, name: string, present: boolean) {
  await page.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await expect(panel.getByRole("checkbox", { name: `Coil ${name}`, exact: true })).toHaveCount(present ? 1 : 0);
  await panel.getByRole("button", { name: "Close layers panel" }).click();
}

test("CAD layer slider isolates each layer and restores all layers", async ({ page }, testInfo) => {
  await page.addInitScript(() => { (window as any).__cadLayered = true; (window as any).__cadNoVias = true; });
  const dialog = await openImport(page);
  const slider = dialog.getByRole("slider", { name: "Preview layer" });
  const steps = dialog.getByRole("group", { name: "Layer isolation" });
  const traces = dialog.locator('div[role="img"][aria-label="CAD import preview"] > svg path');
  await expect(slider).toHaveAttribute("aria-valuetext", "All");
  await expect(traces).toHaveCount(5);

  await slider.focus();
  await slider.press("ArrowRight");
  await expect(slider).toHaveAttribute("aria-valuetext", "Layer 1");
  await expect(traces).toHaveCount(4);
  await slider.press("ArrowRight");
  await expect(slider).toHaveAttribute("aria-valuetext", "Layer 2");
  await expect(traces).toHaveCount(1);
  await steps.getByRole("button", { name: "All", exact: true }).click();
  await expect(traces).toHaveCount(5);
  await steps.getByRole("button", { name: "Layer 1", exact: true }).click();
  await expect(traces).toHaveCount(4);

  const stepBox = (await steps.boundingBox())!;
  const zoomBox = (await dialog.getByRole("group", { name: "Zoom controls" }).boundingBox())!;
  expect(stepBox.x + stepBox.width).toBeLessThan(zoomBox.x);
  expect(Math.abs(stepBox.y + stepBox.height / 2 - zoomBox.y - zoomBox.height / 2)).toBeLessThan(2);
  await page.screenshot({ path: testInfo.outputPath("cad-layer-slider.png") });

  // Side-panel visibility changes and the slider share the same layer state.
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const display = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await display.getByRole("radio", { name: "Layers", exact: true }).check();
  await expect(display.getByRole("checkbox", { name: "Show layer 0", exact: true })).toBeChecked();
  await expect(display.getByRole("checkbox", { name: "Show layer 1", exact: true })).not.toBeChecked();
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await steps.getByRole("button", { name: "Layer 2", exact: true }).click();
  await expect(traces).toHaveCount(1);
  const mobileStepBox = (await steps.boundingBox())!;
  const mobileZoomBox = (await dialog.getByRole("group", { name: "Zoom controls" }).boundingBox())!;
  expect(Math.abs(mobileStepBox.y - mobileZoomBox.y)).toBeLessThan(2);
  await page.screenshot({ path: testInfo.outputPath("cad-layer-slider-mobile.png") });
});

test("shared editing tools measure and edit CAD drafts, then keep those edits in motor preview", async ({ page }, testInfo) => {
  await page.addInitScript(() => { (window as any).__cadNoVias = true; });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("toolbar", { name: "CAD import tools" });
  const summary = dialog.getByText(/\d+ lines,/);
  const toolNames = await tools.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getAttribute("aria-label")).filter(Boolean));
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("2 lines");
  await tools.getByRole("button", { name: "Undo simplify", exact: true }).click();
  await expect(summary).toContainText("4 lines");
  await tools.getByRole("button", { name: "Toggle measure tool" }).click();
  const frame = dialog.getByRole("img", { name: "CAD import preview", exact: true });
  for (const x of [0, 2]) {
    const point = await frame.locator(":scope > svg > g").evaluate((group, x) => {
      const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
      const point = new DOMPoint(x, 0).matrixTransform(matrix);
      return { x: point.x, y: point.y };
    }, x);
    await page.mouse.click(point.x, point.y);
  }
  await expect(tools.getByRole("status").filter({ hasText: "click again" })).toContainText("2.00 mm");
  await expect(dialog.getByRole("img", { name: "Measurement 2.00 mm", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Set coil terminals" }).click();
  const command = dialog.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await expect(tools.getByRole("button", { name: "Toggle measure tool" })).toHaveAttribute("aria-pressed", "false");
  const endpoint = dialog.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true });
  await endpoint.focus();
  await page.keyboard.press("Enter");
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(dialog.getByRole("img", { name: "Coil A Driver end, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("2 lines");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const motor = coilWorkspace(page);
  const motorTools = motor.getByRole("toolbar", { name: "Coil preview tools" });
  expect(await motorTools.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getAttribute("aria-label")).filter(Boolean))).toEqual(toolNames);
  await expect(motor.getByRole("group", { name: "Zoom controls" }).getByRole("button", { name: "Zoom window", exact: true })).toBeVisible();
  await expect(motor.getByRole("img", { name: "Coil A Driver end, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await motorTools.getByRole("button", { name: "Toggle measure tool" }).click();
  for (const x of [0, 2]) {
    const point = await motor.locator('[aria-label="Segment selection preview"] svg > g').evaluate((group, x) => {
      const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
      const point = new DOMPoint(x, 0).matrixTransform(matrix);
      return { x: point.x, y: point.y };
    }, x);
    await page.mouse.click(point.x, point.y);
  }
  await expect(motorTools.getByRole("status").filter({ hasText: "click again" })).toContainText("2.00 mm");
  await expect(motor.getByRole("img", { name: "Measurement 2.00 mm", exact: true })).toBeVisible();
  await motorTools.getByRole("button", { name: "Toggle measure tool" }).click();
  await motor.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const motorCommand = motor.getByRole("region", { name: "Set coil terminals", exact: true });
  await motorCommand.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await motorCommand.getByRole("button", { name: "Flip", exact: true }).click();
  await motorCommand.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(motor.getByRole("img", { name: "Coil A Driver end, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await motor.getByRole("button", { name: "Layers", exact: true }).click();
  const layers = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await layers.getByRole("checkbox", { name: "Coil A", exact: true }).uncheck();
  await expect(motor.getByRole("img", { name: /Coil A Driver end/ })).toHaveCount(0);
  await layers.getByRole("checkbox", { name: "Coil A", exact: true }).check();
  await layers.getByRole("button", { name: "Close layers panel" }).click();
  await revisitWorkspace(page);
  await expect(motor.getByRole("img", { name: "Coil A Driver end, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("shared-motor-editor.png") });
});

test("Routing mirrors imported copper and its picked endpoints without reassigning their roles", async ({ page }) => {
  const { command } = await openTerminalTool(page);
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  const motor = coilWorkspace(page);
  await expect(motor.getByRole("img", { name: "Coil A Driver end, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await selectDesignPanel(page, "Routing");
  const panel = motor.getByRole("dialog", { name: "Routing", exact: true });
  for (const [label, marker] of [
    ["Mirror left/right (X)", "Coil A Driver end, L0, X 2 mm, Y 0 mm"],
    ["Mirror up/down (Y)", "Coil A Driver end, L0, X 2 mm, Y 2 mm"],
    ["Reverse layers (Z)", "Coil A Driver end, L1, X 2 mm, Y 2 mm"],
  ]) {
    await panel.getByRole("button", { name: label, exact: true }).click();
    await expect(motor.getByRole("img", { name: marker, exact: true })).toBeVisible();
  }
  await expect(panel.getByRole("group", { name: "Imported CAD pattern", exact: true })).toBeVisible();
  for (const label of ["Mirror left/right (X)", "Mirror up/down (Y)", "Reverse layers (Z)"]) {
    await panel.getByRole("button", { name: label, exact: true }).click();
  }
  await expect(motor.getByRole("img", { name: "Coil A Driver end, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
});

test("motor tool feedback stays inside the toolbar instead of behind viewport presets", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const motor = coilWorkspace(page);
  const toolbar = motor.getByRole("toolbar", { name: "Coil preview tools", exact: true });
  const presets = motor.getByRole("group", { name: "Viewport view", exact: true });
  const feedback = toolbar.getByRole("status").filter({ hasText: "Choose the first segment." });
  for (const width of [1280, 1600, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await motor.getByRole("button", { name: "Top-down", exact: true }).click();
    const before = await toolbar.boundingBox();
    await toolbar.getByRole("button", { name: "Chain", exact: true }).click();
    await expect(feedback).toHaveText("Choose the first segment.");
    expect(await toolbar.boundingBox()).toEqual(before);
    for (const view of ["Top-down", "Front", "Left", "3D fields and heat"]) {
      await presets.getByRole("button", { name: view, exact: true }).click();
      const bar = (await toolbar.boundingBox())!;
      const hint = (await feedback.boundingBox())!;
      const modes = (await presets.boundingBox())!;
      expect(hint.y).toBeGreaterThanOrEqual(bar.y);
      expect(hint.y + hint.height).toBeLessThanOrEqual(bar.y + bar.height);
      expect(hint.x).toBeGreaterThanOrEqual(bar.x);
      expect(hint.x + hint.width).toBeLessThanOrEqual(bar.x + bar.width);
      expect(modes.y).toBeGreaterThan(bar.y + bar.height);
    }
    await page.screenshot({ path: testInfo.outputPath(`toolbar-chain-feedback-${width}.png`) });
    await motor.getByRole("button", { name: "Top-down", exact: true }).click();
    await toolbar.getByRole("button", { name: "Select", exact: true }).click();
  }
});

test("CAD terminal editing works on mobile and changing tools cancels unapplied drafts", async ({ page }) => {
  await page.addInitScript(() => { (window as any).__cadNoVias = true; });
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("toolbar", { name: "CAD import tools" });
  await dialog.getByRole("button", { name: "Set coil terminals" }).click();
  const command = dialog.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toHaveCount(0);
  await command.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(dialog.getByRole("img", { name: "Coil A Driver end, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(command).toHaveCount(0);
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate(element => element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("CAD Layers combines reciprocal phase-layer sorting with display options without resizing the viewer", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const trigger = dialog.getByRole("button", { name: "Layers", exact: true });
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await expect(dialog.getByRole("button", { name: "Display", exact: true })).toHaveCount(0);
  const frame = dialog.getByRole("img", { name: "CAD import preview", exact: true });
  const traces = frame.locator(":scope > svg path");
  const vias = frame.locator(":scope > svg circle");
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    const before = await frame.boundingBox();
    const rail = dialog.getByRole("toolbar", { name: "Preview side tools" });
    await expect(rail).toHaveAttribute("aria-orientation", "vertical");
    const railBounds = (await rail.boundingBox())!;
    expect(railBounds.x).toBeCloseTo(before!.x + before!.width, 0);
    expect(railBounds.y).toBeCloseTo(before!.y, 0);
    await expect(panel).toBeHidden();
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(panel).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(await frame.boundingBox()).toEqual(before);
    await expect(panel.getByRole("checkbox", { name: "Show phase waveform" })).toHaveCount(0);
    await expect(panel.getByText("Phases and coils", { exact: true })).toHaveCount(0);
    await panel.getByRole("radio", { name: "Phases", exact: true }).check();
    await panel.getByRole("checkbox", { name: "Coil B", exact: true }).uncheck();
    await expect(traces).toHaveCount(2);
    await panel.getByRole("radio", { name: "Layers", exact: true }).check();
    await expect(panel.getByRole("checkbox", { name: "Coil B", exact: true })).toHaveCount(0);
    await expect(panel.getByRole("checkbox", { name: /^Show layer / })).toHaveCount(2);
    for (const layer of [1, 2]) {
      const group = panel.getByRole("group", { name: `Layer ${layer}`, exact: true });
      await expect(group.getByRole("button", { name: `Move selection to A, layer ${layer}`, exact: true })).toHaveText("Phase A");
      await expect(group.getByRole("button", { name: `Move selection to B, layer ${layer}`, exact: true })).toHaveText("Phase B");
    }
    await expect(traces).toHaveCount(2);
    expect(await frame.boundingBox()).toEqual(before);
    await panel.getByRole("checkbox", { name: "Show layer 0", exact: true }).uncheck();
    await expect(traces).toHaveCount(0);
    await panel.getByRole("checkbox", { name: "Show layer 0", exact: true }).check();
    await expect(traces).toHaveCount(2);
    await panel.getByRole("radio", { name: "Centerlines", exact: true }).check();
    await expect.poll(() => traces.first().evaluate((path) => {
      const matrix = (path as SVGGraphicsElement).getScreenCTM()!;
      return Number(getComputedStyle(path).strokeWidth.replace("px", "")) * Math.abs(matrix.a);
    })).toBeCloseTo(1, 2);
    await panel.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
    await expect(vias).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`cad-layers-${viewport.width}.png`) });
    const bounds = (await panel.boundingBox())!;
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(railBounds.x + 4);
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height);
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();
    await expect(dialog).toBeVisible();
    await trigger.click();
    await expect(panel.getByRole("radio", { name: "Layers", exact: true })).toBeChecked();
    await expect(panel.getByRole("radio", { name: "Centerlines", exact: true })).toBeChecked();
    await expect(panel.getByRole("checkbox", { name: "Show vias", exact: true })).not.toBeChecked();
    await panel.getByRole("radio", { name: "Layers", exact: true }).focus();
    await page.keyboard.press("ArrowLeft");
    await expect(panel.getByRole("radio", { name: "Phases", exact: true })).toBeChecked();
    await expect(panel.getByRole("checkbox", { name: "Coil B", exact: true })).not.toBeChecked();
    await panel.getByRole("checkbox", { name: "Coil B", exact: true }).check();
    await panel.getByRole("radio", { name: "Traces", exact: true }).check();
    await panel.getByRole("checkbox", { name: "Show vias", exact: true }).check();
    await panel.getByRole("button", { name: "Close layers panel" }).click();
    await expect(panel).toBeHidden();
    // An outside click, a repeat trigger click, and the Close button all dismiss.
    await trigger.click();
    await expect(panel).toBeVisible();
    await dialog.getByRole("heading", { name: "Import CAD", exact: true }).click();
    await expect(panel).toBeHidden();
    await trigger.click();
    await trigger.click();
    await expect(panel).toBeHidden();
  }
});

test("CAD import viewer fills its container after resizing without distorting traces", async ({ page }) => {
  const dialog = await openImport(page);
  const frame = dialog.getByRole("img", { name: "CAD import preview", exact: true });
  for (const viewport of [{ width: 1280, height: 800 }, { width: 1600, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await expect.poll(() => frame.evaluate((element) => {
      const parent = element.parentElement!;
      return Math.abs(element.clientHeight - parent.clientHeight);
    })).toBeLessThanOrEqual(1);
    await expect.poll(() => frame.locator(":scope > svg > g").evaluate((group) => {
      const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
      return Math.abs(Math.abs(matrix.a) - Math.abs(matrix.d));
    })).toBeLessThan(0.01);
    const tools = dialog.getByRole("group", { name: "Segment selection tools" });
    await tools.getByRole("button", { name: "Select", exact: true }).click();
    await clickTrace(page, .5, 0);
    await expect(tools).toContainText("1 selected");
    await page.keyboard.press("Escape");
    expect(await dialog.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
  }
});

test("source-layer assignments preserve coil visibility and import simplification is reversible", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const summary = dialog.getByText(/\d+ lines,/);
  await expect(summary).toContainText("4 lines");
  await expect(dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" })).not.toBeChecked();
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expectImportCoil(page, "holes", false);
  const preview = dialog.locator('div[role="img"][aria-label="CAD import preview"] > svg');
  expect(await preview.locator("path").evaluateAll(paths => new Set(paths.map(p => p.getAttribute("stroke"))).size)).toBe(2);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await panel.getByRole("checkbox", { name: "Coil B", exact: true }).uncheck();
  await expect(preview.locator("path")).toHaveCount(2);
  await panel.getByRole("checkbox", { name: "Coil B", exact: true }).check();
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" }).check();
  await expect(summary).toContainText("2 lines");
  await page.screenshot({ path: testInfo.outputPath("cad-layer-assignments.png") });
  await dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" }).uncheck();
  await expect(summary).toContainText("4 lines");
  await dialog.getByLabel("Coil for source layer L0_B").fill("");
  await expect(dialog.getByRole("alert").filter({ hasText: "coil name" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toHaveCount(0);
  await dialog.getByLabel("Coil for source layer L0_B").fill("B");
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toBeVisible();
});

test("imported motor preview simplifies saved geometry and supports undo beside Measure", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expectImportCoil(page, "holes", false);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await expect(dialog).toBeHidden();
  await openCoilPreview(page);
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status").filter({ hasText: "merged" })).toContainText("2 line(s) merged");
  await page.screenshot({ path: testInfo.outputPath("cad-simplify-toolbar.png") });
  await tools.getByRole("button", { name: "Undo simplify" }).click();
  await expect(tools.getByRole("status").filter({ hasText: "undone" })).toBeVisible();
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status").filter({ hasText: "merged" })).toContainText("2 line(s) merged");
  // Ctrl+Z reaches the same undo as the toolbar button in the motor modal.
  await page.keyboard.press("Control+z");
  await expect(tools.getByRole("status").filter({ hasText: "undone" })).toBeVisible();
});

async function tracePoint(page: Page, x: number, y: number) {
  return await page.getByRole("listbox", { name: "Segment selection preview" }).locator("svg > g").evaluate((group, point) => {
    const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
    const screen = new DOMPoint(point.x, point.y).matrixTransform(matrix);
    return { x: screen.x, y: screen.y };
  }, { x, y });
}

async function clickTrace(page: Page, x: number, y: number, shift = false) {
  const point = await tracePoint(page, x, y);
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.click(point.x, point.y);
  if (shift) await page.keyboard.up("Shift");
}

async function dragBox(page: Page, a: [number, number], b: [number, number]) {
  const start = await tracePoint(page, ...a), end = await tracePoint(page, ...b);
  await page.mouse.move(start.x, start.y); await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 8 }); await page.mouse.up();
}

async function newCoil(page: Page, name: string) {
  await page.getByRole("button", { name: "Selection actions", exact: true }).click();
  await page.getByRole("menuitem", { name: "Change to coil…", exact: true }).hover();
  await page.getByRole("menuitem", { name: "New coil…", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Change to a new coil", exact: true });
  await dialog.getByLabel("Coil name").fill(name);
  await dialog.getByRole("button", { name: "Move selection", exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function changeLayer(page: Page, layer: number) {
  await page.getByRole("button", { name: "Selection actions", exact: true }).click();
  await page.getByRole("menuitem", { name: "Change to layer…", exact: true }).hover();
  await page.getByRole("menuitem", { name: `Layer ${layer}`, exact: true }).click();
}

test("selection context menu changes coil or layer separately and preserves selection on dismissal", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await expect(tools.getByPlaceholder("Keep coil")).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Selection actions" })).toBeDisabled();
  await clickTrace(page, .5, 0);
  const point = await tracePoint(page, .5, 0);
  await page.mouse.click(point.x, point.y, { button: "right" });
  await expect(page.getByRole("menuitem", { name: "Change to coil…", exact: true })).toBeVisible();
  await expect(page.getByRole("menu", { name: "Selection actions", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(tools).toContainText("1 selected");
  await expect(dialog).toBeVisible();
  await page.mouse.click(point.x, point.y, { button: "right" });
  await page.getByRole("menuitem", { name: "Change to coil…", exact: true }).hover();
  await page.getByRole("menuitem", { name: "B", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 0/ })).toHaveCount(1);
  await expect(tools).toContainText("1 selected");
  await page.mouse.click(point.x, point.y, { button: "right" });
  await page.getByRole("menuitem", { name: "Change to layer…", exact: true }).hover();
  await page.getByRole("menuitem", { name: "Layer 2", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  await tools.getByRole("button", { name: "Undo assignment" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 0/ })).toHaveCount(1);
});

test("outside clicks dismiss context menus and submenus while selecting in CAD and motor viewers", async ({ page }) => {
  const cad = await openImport(page);
  for (const viewer of ["cad", "motor"]) {
    if (viewer === "motor") {
      await cad.getByRole("button", { name: "Open with this geometry" }).click();
      await openCoilPreview(page);
    }
    const dialog = viewer === "cad" ? cad : coilWorkspace(page);
    const tools = dialog.getByRole("group", { name: "Segment selection tools" });
    await clickTrace(page, .5, 0);
    const frame = dialog.getByRole("img", { name: viewer === "cad" ? "CAD import preview" : "Coil preview", exact: true });
    const bounds = (await frame.boundingBox())!;
    const menu = page.getByRole("menu", { name: "Selection actions", exact: true });
    const openMenu = async () => {
      await page.mouse.click(bounds.x + bounds.width * .8, bounds.y + bounds.height * (viewer === "motor" ? .45 : .15), { button: "right" });
      await expect(menu).toBeVisible();
    };
    await openMenu();
    if (viewer === "cad") await dialog.getByRole("heading", { name: "Import CAD", exact: true }).click();
    else await dialog.getByRole("toolbar", { name: "Coil preview tools", exact: true }).click({ position: { x: 1, y: 1 } });
    await expect(menu).toBeHidden();
    await expect(dialog).toBeVisible();
    await expect(tools).toContainText("1 selected");
    await openMenu();
    await page.getByRole("menuitem", { name: "Change to coil…", exact: true }).hover();
    const submenu = page.getByRole("menu", { name: "Change to coil", exact: true });
    await expect(submenu).toBeVisible();
    await clickTrace(page, 1.5, 0);
    await expect(menu).toBeHidden();
    await expect(submenu).toBeHidden();
    await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveAttribute("aria-selected", "true");
    await openMenu();
    await dragBox(page, [-.1, -.1], [2.1, .1]);
    await expect(menu).toBeHidden();
    await expect(tools).toContainText("2 selected");
  }
});

for (const sort of ["Phases", "Layers"]) {
test(`nested destinations sorted by ${sort} support Move to, direct clicks, and independent visibility`, async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await panel.getByRole("radio", { name: sort, exact: true }).check();
  const destination = panel.getByRole("group", { name: sort === "Phases" ? "Phase B" : "Layer 2", exact: true });
  await expect(panel.getByRole("button", { name: "Move selection to B, layer 1", exact: true })).toBeDisabled();
  await expect(destination.getByRole("button", { name: "Move selection to B, layer 2", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await clickTrace(page, .5, 0);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await destination.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click({ button: "right" });
  await page.getByRole("menuitem", { name: "Move to", exact: true }).click();
  await expect(panel).toBeVisible();
  await expect(tools).toContainText("1 selected");
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  await destination.getByRole("checkbox", { name: "Show B, layer 2", exact: true }).uncheck();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(0);
  await expect(dialog.getByRole("option", { name: /coil A, layer 0/ })).toHaveCount(1);
  await destination.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await expect(destination.getByRole("checkbox", { name: "Show B, layer 2", exact: true })).toBeChecked();
  await panel.getByRole("radio", { name: sort === "Phases" ? "Layers" : "Phases", exact: true }).check();
  await expect(panel.getByRole("checkbox", { name: "Show B, layer 2", exact: true })).toBeChecked();
  await panel.getByRole("radio", { name: "Phases", exact: true }).check();
  await panel.getByRole("button", { name: "Move selection to Phase A", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil A, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("nested-coil-layers.png") });
});
}

test("outside clicks dismiss destination and toolbar menus without consuming the next action", async ({ page }) => {
  const dialog = await openImport(page);
  await clickTrace(page, .5, 0);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await panel.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click({ button: "right" });
  const destinationMenu = page.getByRole("menu", { name: "Move selection", exact: true });
  await expect(destinationMenu).toBeVisible();
  const visibility = panel.getByRole("checkbox", { name: "Show B, layer 1", exact: true });
  await visibility.uncheck();
  await expect(destinationMenu).toBeHidden();
  await expect(visibility).not.toBeChecked();
  await expect(panel).toBeVisible();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil A, layer 0/ })).toHaveAttribute("aria-selected", "true");
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await dialog.getByRole("button", { name: "Selection actions", exact: true }).click();
  await page.getByRole("menuitem", { name: "Change to layer…", exact: true }).hover();
  await expect(page.getByRole("menu", { name: "Change to layer", exact: true })).toBeVisible();
  await clickTrace(page, 1.5, 0);
  await expect(page.getByRole("menu", { name: "Selection actions", exact: true })).toBeHidden();
  await expect(page.getByRole("menu", { name: "Change to layer", exact: true })).toBeHidden();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveAttribute("aria-selected", "true");
});

test("nested motor layers move selections on mobile and toggle only their own coil/layer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const motor = coilWorkspace(page);
  await clickTrace(page, .5, 0);
  await motor.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await panel.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await expect(motor.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  const canvas = motor.getByTestId("coil-annotations");
  const overlay = motor.getByRole("listbox", { name: "Segment selection preview" }).locator("svg > g");
  const camera = (await overlay.getAttribute("transform"))!;
  const before = Number(await canvas.getAttribute("data-segments"));
  await panel.getByRole("checkbox", { name: "Show B, layer 2", exact: true }).uncheck();
  await expect.poll(async () => Number(await canvas.getAttribute("data-segments"))).toBeLessThan(before);
  await expect(overlay).toHaveAttribute("transform", camera);
  await expect(motor.getByRole("option", { name: /coil A, layer 0/ })).toHaveCount(1);
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await motor.getByRole("button", { name: "Undo assignment" }).click();
  await expect(motor.getByRole("option", { name: /Segment 1, coil A, layer 0/ })).toHaveCount(1);
});

test("assignment menus are keyboard accessible and cancelling a new coil preserves geometry", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await clickTrace(page, .5, 0);
  for (const cancel of [true, false]) {
    await tools.getByRole("button", { name: "Selection actions" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menuitem", { name: "Change to coil…", exact: true })).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("menuitem", { name: "A", exact: true })).toBeFocused();
    // Stay in keyboard navigation. Moving the mouse across the parent menu
    // can legitimately close a keyboard-open submenu before the click lands.
    await page.keyboard.press("End");
    await expect(page.getByRole("menuitem", { name: "New coil…", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    const nameDialog = page.getByRole("dialog", { name: "Change to a new coil", exact: true });
    await expect(nameDialog.getByLabel("Coil name")).toBeFocused();
    await expect(nameDialog.getByRole("button", { name: "Move selection" })).toBeDisabled();
    await nameDialog.getByLabel("Coil name").fill("  C  ");
    await page.keyboard.press(cancel ? "Escape" : "Enter");
    await expect(nameDialog).toHaveCount(0);
    await expect(tools).toContainText("1 selected");
    await expect(dialog.getByRole("option", { name: new RegExp(`Segment 1, coil ${cancel ? 'A' : 'C'}, layer 0`) })).toHaveCount(1);
  }
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "CAD import layers" }).getByRole("group", { name: "Phase C", exact: true }).getByRole("button", { name: "Move selection to C, layer 2", exact: true })).toBeVisible();
});

test("import selection toggles segments, reassigns coil and layer, and supports undo", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0, true);
  await expect(tools).toContainText("2 selected");
  await clickTrace(page, .5, 0, true);
  await expect(tools).toContainText("1 selected");
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await page.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await page.getByRole("button", { name: "Close layers panel" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil B, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("cad-segment-selection.png") });
  await tools.getByRole("button", { name: "Undo assignment" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveCount(1);
});

test("Ctrl+Z undoes the last assignment, simplify and terminal edit", async ({ page }) => {
  // No vias keeps coil A's open ends unambiguous, matching the other
  // terminal tests, so the default endpoints are ready to apply.
  await page.addInitScript(() => { (window as any).__cadNoVias = true; });
  const dialog = await openImport(page);
  const selection = dialog.getByRole("group", { name: "Segment selection tools" });
  const tools = dialog.getByRole("toolbar", { name: "CAD import tools" });
  const markers = dialog.getByRole("group", { name: "Coil terminal markers" });
  // Assignment (also proves the shortcut, not just the toolbar button).
  await clickTrace(page, .5, 0);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await page.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await page.getByRole("button", { name: "Close layers panel" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  await page.keyboard.press("Control+z");
  await expect(dialog.getByRole("option", { name: /Segment 1, coil A, layer 0/ })).toHaveCount(1);
  await expect(selection.getByRole("button", { name: "Undo assignment" })).toHaveCount(0);
  // Simplify, undone with the platform modifier.
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status")).toContainText("merged");
  await page.keyboard.press("Meta+z");
  await expect(tools.getByRole("status")).toContainText("undone");
  // Terminal change.
  await dialog.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const terminalPanel = dialog.getByRole("region", { name: "Set coil terminals", exact: true });
  await terminalPanel.getByRole("button", { name: "Select driver end for coil A", exact: true }).click();
  await terminalPanel.getByRole("button", { name: "Keep current points", exact: true }).click();
  await terminalPanel.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(markers.getByRole("img")).toHaveCount(2);
  await page.keyboard.press("Control+z");
  await expect(markers.getByRole("img")).toHaveCount(0);
});

test("chain assignments persist into the motor preview and selection tools work there too", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Chain", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0);
  await expect(tools).toContainText("2 selected");
  await newCoil(page, "D");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const modalTools = page.getByRole("group", { name: "Segment selection tools" });
  await modalTools.getByRole("button", { name: "Chain", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0);
  await expect(modalTools).toContainText("2 selected");
  await newCoil(page, "E");
  await changeLayer(page, 2);
  await expect(page.getByRole("option", { name: /Segment 1, coil E, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("coil-segment-selection.png") });
  await revisitWorkspace(page);
  await page.getByRole("group", { name: "Segment selection tools" }).getByRole("button", { name: "Select", exact: true }).click();
  await expect(page.getByRole("option", { name: /Segment 1, coil E, layer 1/ })).toHaveCount(1);
});

test("default click and drag selection works in CAD and motor viewers without a box tool", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await expect(tools.getByRole("button", { name: "Box", exact: true })).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Pan", exact: true })).toHaveCount(0);
  await clickTrace(page, .5, 0);
  await expect(tools).toContainText("1 selected");
  await dragBox(page, [.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("0 selected");
  await dragBox(page, [1.1, -.1], [.1, .1]);
  await expect(tools).toContainText("2 selected");
  await tools.getByRole("button", { name: "Chain", exact: true }).click();
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("1 selected");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await openCoilPreview(page);
  const motor = coilWorkspace(page);
  const motorTools = motor.getByRole("group", { name: "Segment selection tools" });
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(motorTools).toContainText("1 selected");
  await newCoil(page, "D");
  await expect(motor.getByRole("option", { name: /Segment 1, coil D/ })).toHaveCount(1);
});

test("touch drag selects, two fingers pan, and three-finger pinch zooms without changing selection", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 3 });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  const start = await tracePoint(page, -.1, -.1);
  const end = await tracePoint(page, 1.1, .1);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ ...start, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ ...end, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(tools).toContainText("1 selected");
  for (const viewer of ["cad", "motor"]) {
  if (viewer === "motor") {
    await dialog.getByRole("button", { name: "Open with this geometry" }).click();
    await openCoilPreview(page);
  }
  const activeDialog = viewer === "cad" ? dialog : coilWorkspace(page);
  const activeTools = activeDialog.getByRole("group", { name: "Segment selection tools" });
  const selected = viewer === "cad" ? "1 selected" : "0 selected";
  const frame = activeDialog.getByRole("img", { name: viewer === "cad" ? "CAD import preview" : "Coil preview", exact: true });
  const group = activeDialog.locator('[aria-label="Segment selection preview"] svg > g');
  const before = await group.evaluate(g => { const m = (g as SVGGraphicsElement).getScreenCTM()!; return { s: m.a, x: m.e, y: m.f }; });
  const bounds = (await frame.boundingBox())!;
  const points = [
    { id: 1, x: bounds.x + bounds.width * .35, y: bounds.y + bounds.height * .4 },
    { id: 2, x: bounds.x + bounds.width * .6, y: bounds.y + bounds.height * .4 },
  ];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points.slice(0, 1) });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points });
  const panned = points.map(p => ({ ...p, x: p.x + 20, y: p.y + 15 }));
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: panned });
  await expect.poll(() => group.evaluate(g => (g as SVGGraphicsElement).getScreenCTM()!.e)).toBeCloseTo(before.x + 20, 0);
  await expect.poll(() => group.evaluate(g => (g as SVGGraphicsElement).getScreenCTM()!.f)).toBeCloseTo(before.y + 15, 0);
  await expect(activeDialog.getByRole("button", { name: "Reset zoom", exact: true })).toHaveText("1×");
  await expect(activeTools).toContainText(selected);
  const triple = [...panned, { id: 3, x: bounds.x + bounds.width * .475 + 20, y: bounds.y + bounds.height * .65 + 15 }];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: triple });
  const center = { x: triple.reduce((sum, p) => sum + p.x, 0) / 3, y: triple.reduce((sum, p) => sum + p.y, 0) / 3 };
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: triple.map(p => ({ ...p, x: center.x + 2 * (p.x - center.x), y: center.y + 2 * (p.y - center.y) })) });
  await expect.poll(() => group.evaluate(g => (g as SVGGraphicsElement).getScreenCTM()!.a)).toBeCloseTo(before.s * 2, 0);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(activeTools).toContainText(selected);
  await activeDialog.getByRole("button", { name: "Reset zoom", exact: true }).click();
  const tap = await tracePoint(page, .5, 0);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ ...tap, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(activeTools).toContainText("1 selected");
  }
  await cdp.detach();
});

test("box selection is always by direction and never shifts the preview", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  const toolbar = dialog.getByRole("toolbar", { name: "CAD import tools" });
  await expect(tools.getByRole("button", { name: "Box", exact: true })).toHaveCount(0);
  await expect(tools.getByLabel("Box coverage")).toHaveCount(0);
  await expect(tools.getByLabel("Box selection action")).toHaveCount(0);
  const preview = dialog.getByRole("region", { name: "CAD import preview" });
  const before = await preview.boundingBox();
  // Drag right selects contained segments only…
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("1 selected");
  await expect(toolbar.getByRole("status")).toContainText("Right-click");
  // …and the drawing below the divider does not move when the hint appears.
  expect(await preview.boundingBox()).toEqual(before);
  // Drag left selects anything crossed.
  await dragBox(page, [1.1, .1], [.1, -.1]);
  await expect(tools).toContainText("2 selected");
  expect(await preview.boundingBox()).toEqual(before);
  // Shift adds to the existing selection.
  await page.keyboard.down("Shift");
  await dragBox(page, [-.1, 1.9], [1.1, 2.1]);
  await page.keyboard.up("Shift");
  await expect(tools).toContainText("3 selected");
  await tools.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(tools).toContainText("0 selected");
  await expect(toolbar.getByRole("status")).toHaveText("");
  expect(await preview.boundingBox()).toEqual(before);
  await dialog.getByLabel("Import settings").evaluate((element) => element.scrollTo(0, element.scrollHeight));
  expect(await preview.boundingBox()).toEqual(before);
  expect(await dialog.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("keyboard selection and short tooltips work at mobile size", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  for (const name of ["Select", "Chain"]) {
    const button = tools.getByRole("button", { name, exact: true });
    await expect(button.locator("svg")).toHaveAttribute("aria-hidden", "true");
    expect((await button.boundingBox())!.width).toBeLessThanOrEqual(36);
  }
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  const preview = page.getByRole("listbox", { name: "Segment selection preview" });
  await preview.focus(); await page.keyboard.press("ArrowRight"); await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowRight"); await page.keyboard.press("Shift+Enter");
  await expect(tools).toContainText("2 selected");
  await page.keyboard.press("Shift+Enter"); await expect(tools).toContainText("1 selected");
  await page.keyboard.press("Escape"); await expect(tools).toContainText("0 selected");
  const titles = await dialog.locator("[title]").evaluateAll((elements) => elements.map((e) => e.getAttribute("title")!));
  expect(titles.every((title) => title.length <= 140)).toBe(true);
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("reimport waits for confirmation before discarding segment assignments", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await clickTrace(page, .5, 0);
  await newCoil(page, "C");
  await dialog.getByLabel("Trace width (mm)", { exact: true }).fill("0.5");
  await expect(dialog.getByRole("button", { name: "Reimport", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Reimport", exact: true }).click();
  await expectImportCoil(page, "C", true);
  await page.evaluate(() => { (window as any).__cadConfirmResult = true; });
  await dialog.getByRole("button", { name: "Reimport", exact: true }).click();
  await expectImportCoil(page, "C", false);
  await expect(tools).toContainText("0 selected");
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toBeVisible();
});

test("generated motor geometry becomes editable only after confirmation", async ({ page }) => {
  await gotoDesignApp(page);
  await openCoilPreview(page);
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Edit segments", exact: true }).click();
  await expect(tools.getByRole("button", { name: "Edit segments", exact: true })).toBeEnabled();
  await expect(page.getByRole("group", { name: "Segment selection tools" })).toHaveCount(0);
  await page.evaluate(() => { (window as any).__cadConfirmResult = true; });
  await tools.getByRole("button", { name: "Edit segments", exact: true }).click();
  const selection = page.getByRole("group", { name: "Segment selection tools" });
  await expect(selection.getByRole("button", { name: "Select", exact: true })).toHaveAttribute("aria-pressed", "true");
  await clickTrace(page, .5, 0);
  await expect(selection).toContainText("1 selected");
});

test("routing source shows the imported filename in its trigger and dropdown after edits", async ({ page }) => {
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await selectDesignPanel(page, "Routing");
  const source = page.getByRole("button", { name: "Routing source", exact: true });
  await expect(source).toContainText("coil-leads.dxf");
  await source.click();
  await expect(page.getByRole("option", { name: "coil-leads.dxf", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await openCoilPreview(page);
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await page.getByRole("tab", { name: /^Design/i }).click();
  await selectDesignPanel(page, "Routing");
  await expect(source).toContainText("coil-leads.dxf");
});

test("reviewing coil ends keeps the simulation results dock open", async ({ page }) => {
  const imported = await openImport(page);
  await imported.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  const notice = dock.getByRole("status", { name: "Inferred coil ends", exact: true });
  await notice.getByRole("button", { name: "Review", exact: true }).click();
  await expect(dock).toBeVisible();
  await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("dialog", { name: "Coil terminals", exact: true })).toBeVisible();
  await expect(page.getByRole("toolbar", { name: "Design side tools", exact: true }).getByRole("button", { name: "Set coil terminals", exact: true })).toHaveAttribute("aria-expanded", "true");
});
