import { expect, test } from "@playwright/test";
import { gotoDesignApp, openCoilPreview } from "./helpers";
import { readFileSync } from "node:fs";
import { installViewMenu, nativeViewAction as nativeAction, viewMenuSnapshot as snapshot, viewMenuChecked as checked } from "./view-menu-helpers";
const groups = JSON.parse(readFileSync(new URL("../src/lib/viewMenu.json", import.meta.url), "utf8")) as { id: string; label: string }[][];

// Exercise the real state/ownership bridge at its native IPC boundary.
test.beforeEach(async ({ page }) => { await installViewMenu(page); });

test("View Zoom submenu owns extents while window stays synchronized with its viewport button", async ({ page }) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  expect(groups[6].map(item => item.id)).toEqual(["view:zoom-extents", "view:zoom-window"]);
  const controls = page.getByRole("group", { name: "Zoom controls", exact: true });
  await expect(controls.getByRole("button", { name: "Zoom extents", exact: true })).toHaveCount(0);
  for (const [label, id] of [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    const viewer = page.getByTestId(`coil-${id}`);
    await expect(viewer).toHaveAttribute("data-camera", /position/);
    await controls.getByRole("button", { name: "Reset view", exact: true }).click();
    const initial = JSON.parse((await viewer.getAttribute("data-camera"))!);
    await nativeAction(page, "view:zoom-window");
    await expect(controls.getByRole("button", { name: "Zoom window", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => checked(page, "view:zoom-window")).toBe(true);
    await controls.getByRole("button", { name: "Zoom window", exact: true }).click();
    await expect.poll(() => checked(page, "view:zoom-window")).toBe(false);
    await controls.getByRole("button", { name: "Zoom in", exact: true }).click();
    await expect.poll(async () => JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(initial.zoom);
    await nativeAction(page, "view:zoom-extents");
    await expect.poll(async () => JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeCloseTo(initial.zoom, 6);
    await expect.poll(() => checked(page, "view:zoom-extents")).toBe(false);
  }
});

test("view choices live at the viewport top-left and survive both views", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const modes = workspace.getByRole("group", { name: "Viewport view", exact: true });
  const top = modes.getByRole("button", { name: "Top-down", exact: true });
  const iso = modes.getByRole("button", { name: "3D fields and heat", exact: true });
  const toolbar = workspace.getByRole("toolbar", { name: "Coil preview tools", exact: true });
  const tools = (await toolbar.boundingBox())!;
  await expect(toolbar.getByRole("group", { name: "Viewport view", exact: true })).toHaveCount(0);
  const box = (await modes.boundingBox())!;
  const routing = (await workspace.getByRole("dialog", { name: "Routing", exact: true }).boundingBox())!;
  expect(box.x).toBeCloseTo(routing.x + routing.width + 8, 0);
  expect(box.y).toBeCloseTo(tools.y + tools.height + 8, 0);
  await workspace.getByRole("button", { name: "Layers", exact: true }).click();
  const display = workspace.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await expect(display.getByRole("radio", { name: "Top-down", exact: true })).toHaveCount(0);
  await expect(display.getByRole("radio", { name: "3D", exact: true })).toHaveCount(0);
  await iso.click();
  await expect(iso).toHaveAttribute("aria-pressed", "true");
  await expect(workspace.getByTestId("coil-iso")).toBeVisible();
  const viewer = (await workspace.getByTestId("coil-iso").boundingBox())!;
  const viewSwitch = (await modes.boundingBox())!;
  expect(viewSwitch.x).toBeCloseTo(viewer.x + 8, 0);
  expect(viewSwitch.y).toBeCloseTo(viewer.y + 8, 0);
  await expect.poll(() => checked(page, "view:3d")).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("viewport-3d-switch.png") });
  await top.click();
  await expect(workspace.getByTestId("coil-iso")).toHaveCount(0);
  await expect.poll(() => checked(page, "view:top")).toBe(true);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.getByRole("region", { name: "Simulation results", exact: true }).getByRole("button", { name: /3D fields/ })).toHaveCount(0);
});

test("View owns global controls while the side panels retain phase and layer filters", async ({ page }, info) => {
  await gotoDesignApp(page);
  await expect.poll(async () => (await snapshot(page))?.items.length).toBe(groups.flat().length);
  expect((await snapshot(page)).items.map(item => item.id)).toEqual(groups.flat().map(item => item.id));
  expect(groups[3].map(item => item.label)).toEqual(["Pole pitch", "Conductor band widths", "Pole regions"]);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const canvas = workspace.getByTestId("coil-annotations");
  await expect(workspace.getByRole("button", { name: "Display", exact: true })).toHaveCount(0);
  await workspace.getByRole("button", { name: "Layers", exact: true }).click();
  const display = workspace.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await expect(display.getByRole("radio", { name: "Traces", exact: true })).toHaveCount(0);
  await expect(display.getByRole("radio", { name: "Centerlines", exact: true })).toHaveCount(0);
  await display.getByRole("radio", { name: "Layers", exact: true }).check();
  await expect(display.getByRole("checkbox", { name: "Show vias", exact: true })).toHaveCount(0);
  await expect(display.getByRole("checkbox", { name: "Show terminal arrows", exact: true })).toHaveCount(0);
  const copper = display.getByRole("checkbox", { name: "Show layer 0", exact: true });
  await copper.uncheck();
  await expect(copper).not.toBeChecked();
  await copper.check();
  await page.screenshot({ path: info.outputPath("display-copper-layers-only.png") });
  await nativeAction(page, "view:vias");
  await expect.poll(() => checked(page, "view:vias")).toBe(false);
  await expect(canvas).toHaveAttribute("data-vias", "0");
  await nativeAction(page, "view:vias");
  await expect(canvas).toHaveAttribute("data-vias", /[1-9]/);
  await nativeAction(page, "view:centerlines");
  await expect(canvas).toHaveAttribute("data-trace-mode", "centerlines");
  await expect.poll(() => checked(page, "view:traces")).toBe(false);
  await nativeAction(page, "view:terminals");
  await expect.poll(() => checked(page, "view:terminals")).toBe(false);
  await display.getByRole("radio", { name: "Phases", exact: true }).check();
  const layers = workspace.getByRole("dialog", { name: "Coil preview layers", exact: true });
  for (const [id, label] of [["view:pole-pitch", "Show pole-pitch dimension ruler"], ["view:band-widths", "Show band-width diagnostics"], ["view:pole-regions", "Show pole regions"], ["view:waveform", "Show phase waveform"], ["view:one-period", "Show only one repeating section of the pattern"]]) {
    await expect(layers.getByRole("checkbox", { name: label, exact: true })).toHaveCount(0);
    const before = await checked(page, id);
    await nativeAction(page, id);
    await expect.poll(() => checked(page, id)).toBe(!before);
  }
  await nativeAction(page, "view:layer-0");
  await expect(layers.getByRole("checkbox", { name: "Show phase A", exact: true })).toBeChecked();
  await expect(layers.getByRole("combobox", { name: "Pole regions phase", exact: true })).toBeEnabled();
  await layers.getByRole("combobox", { name: "Pole regions phase", exact: true }).selectOption("B");
  await expect(layers.getByRole("combobox", { name: "Pole regions phase", exact: true })).toHaveValue("B");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(layers.getByRole("checkbox", { name: "Show phase A", exact: true })).toBeVisible();
  await expect(layers.getByRole("checkbox", { name: "Show pole regions", exact: true })).toHaveCount(0);
  await layers.getByRole("combobox", { name: "Pole regions phase", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("layers-phase-filters-mobile.png") });
});

test("menu follows the active file and ignores stale events and modal actions", async ({ page }) => {
  await gotoDesignApp(page);
  await expect.poll(async () => (await snapshot(page))?.owner).toBeTruthy();
  const owner = (await snapshot(page)).owner!;
  await nativeAction(page, "view:vias");
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await expect.poll(async () => (await snapshot(page)).items.every(item => !item.enabled)).toBe(true);
  await nativeAction(page, "view:vias");
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
  await expect.poll(async () => (await snapshot(page)).owner).not.toBe(owner);
  await nativeAction(page, "view:3d", owner);
  await expect(page.getByRole("button", { name: "Top-down", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.locator("#file-tab-1").click();
  await expect.poll(() => checked(page, "view:vias")).toBe(false);
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Sensor coil/ }).click();
  await expect.poll(async () => (await snapshot(page)).items.every(item => !item.enabled)).toBe(true);
});

test("mobile view switches remain accessible beside the position/layers controls", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page);
  const modes = page.getByRole("group", { name: "Viewport view", exact: true });
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const bar = page.getByRole("group", { name: "Position bar mode", exact: true });
  const a = (await bar.boundingBox())!, b = (await modes.boundingBox())!;
  expect(b.y + b.height).toBeLessThan(a.y);
  expect(b.x).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width).toBeLessThanOrEqual(346);
  await modes.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await expect(modes.getByRole("button", { name: "3D fields and heat", exact: true })).toHaveAttribute("aria-pressed", "true");
  await modes.getByRole("button", { name: "Top-down", exact: true }).click();
  await expect(bar).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("viewport-switch-mobile.png") });
});
