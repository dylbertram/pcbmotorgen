import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";
import { readFileSync } from "node:fs";
import type { ViewMenuState } from "../src/lib/viewMenu";
const groups = JSON.parse(readFileSync(new URL("../src/lib/viewMenu.json", import.meta.url), "utf8")) as { id: string; label: string }[][];

// Exercise the real state/ownership bridge at its native IPC boundary.
test.beforeEach(async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/viewMenu\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function publishViewMenu(state) { window.__nativeViewMenu = state; }
      export async function listenViewMenu(handler) {
        const listener = e => handler(e.detail); window.addEventListener('native-view-action', listener);
        return () => window.removeEventListener('native-view-action', listener);
      }`,
  }));
});

const snapshot = (page: Page) => page.evaluate(() => (window as any).__nativeViewMenu as ViewMenuState);
async function nativeAction(page: Page, id: string, owner?: string) {
  await page.evaluate(({ id, owner }) => window.dispatchEvent(new CustomEvent("native-view-action", {
    detail: { id, owner: owner ?? (window as any).__nativeViewMenu.owner },
  })), { id, owner });
}
const checked = async (page: Page, id: string) => (await snapshot(page))?.items.find(item => item.id === id)?.checked;

test("view choices live at the viewport bottom-right and survive both views", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const modes = workspace.getByRole("group", { name: "Viewport view", exact: true });
  const top = modes.getByRole("button", { name: "Top-down", exact: true });
  const iso = modes.getByRole("button", { name: "3D fields and heat", exact: true });
  const frame = await workspace.getByRole("img", { name: "Coil preview", exact: true }).boundingBox();
  const box = (await modes.boundingBox())!;
  expect(box.x).toBeGreaterThan(frame!.x + frame!.width / 2);
  expect(box.y).toBeGreaterThan(frame!.y + frame!.height - 80);
  await workspace.getByRole("button", { name: "Display", exact: true }).click();
  const display = workspace.getByRole("dialog", { name: "Coil preview display", exact: true });
  await expect(display.getByRole("radio", { name: "Top-down", exact: true })).toHaveCount(0);
  await expect(display.getByRole("radio", { name: "3D", exact: true })).toHaveCount(0);
  await iso.click();
  await expect(iso).toHaveAttribute("aria-pressed", "true");
  await expect(workspace.getByTestId("coil-iso")).toBeVisible();
  const viewer = (await workspace.getByTestId("coil-iso").boundingBox())!;
  const viewSwitch = (await modes.boundingBox())!;
  expect(viewer.y + viewer.height).toBeLessThanOrEqual(viewSwitch.y);
  await expect.poll(() => checked(page, "view:3d")).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("viewport-3d-switch.png") });
  await top.click();
  await expect(workspace.getByTestId("coil-iso")).toHaveCount(0);
  await expect.poll(() => checked(page, "view:top")).toBe(true);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.getByRole("region", { name: "Simulation results", exact: true }).getByRole("button", { name: /3D fields/ })).toHaveCount(0);
});

test("native checks mirror Display and Layers groups without phase/layer entries", async ({ page }) => {
  await gotoDesignApp(page);
  await expect.poll(async () => (await snapshot(page))?.items.length).toBe(11);
  expect((await snapshot(page)).items.map(item => item.id)).toEqual(groups.flat().map(item => item.id));
  expect(groups[3].map(item => item.label)).toEqual(["Pole pitch", "Conductor band widths", "Pole regions"]);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  await workspace.getByRole("button", { name: "Display", exact: true }).click();
  const display = workspace.getByRole("dialog", { name: "Coil preview display", exact: true });
  await display.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
  await expect.poll(() => checked(page, "view:vias")).toBe(false);
  await nativeAction(page, "view:vias");
  await expect(display.getByRole("checkbox", { name: "Show vias", exact: true })).toBeChecked();
  await nativeAction(page, "view:centerlines");
  await expect(display.getByRole("radio", { name: "Centerlines", exact: true })).toBeChecked();
  await expect.poll(() => checked(page, "view:traces")).toBe(false);
  await nativeAction(page, "view:terminals");
  await expect(display.getByRole("checkbox", { name: "Show terminal arrows", exact: true })).not.toBeChecked();
  await workspace.getByRole("button", { name: "Layers", exact: true }).click();
  const layers = workspace.getByRole("dialog", { name: "Coil preview layers", exact: true });
  for (const [id, label] of [["view:pole-pitch", "Show pole-pitch dimension ruler"], ["view:band-widths", "Show band-width diagnostics"], ["view:pole-regions", "Show pole regions"], ["view:waveform", "Show phase waveform"], ["view:one-period", "Show only one repeating section of the pattern"]]) {
    const control = layers.getByRole("checkbox", { name: label, exact: true });
    const before = await control.isChecked();
    await nativeAction(page, id);
    await expect(control).toBeChecked({ checked: !before });
    await expect.poll(() => checked(page, id)).toBe(!before);
  }
  await nativeAction(page, "view:layer-0");
  await expect(layers.getByRole("checkbox", { name: "Show phase A", exact: true })).toBeChecked();
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
  expect(a.y + a.height).toBeLessThan(b.y);
  expect(b.x).toBeGreaterThanOrEqual(44);
  expect(b.x + b.width).toBeLessThanOrEqual(346);
  await modes.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await expect(modes.getByRole("button", { name: "3D fields and heat", exact: true })).toHaveAttribute("aria-pressed", "true");
  await modes.getByRole("button", { name: "Top-down", exact: true }).click();
  await expect(bar).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("viewport-switch-mobile.png") });
});
