import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";
import type { CadGeometry, SensorGeometry } from "../src/lib/types";

const geometry: SensorGeometry = {
  board_bounds_mm: [0, -2, 8, 2], terminal_markers: [],
  nets: [{
    name: "CL1", trace_width_mm: 0.15, via_size_mm: 0.6, segments: [], vias: [],
    splines: [{ degree: 3, knots: [0, 0, 0, 0, 1, 1, 1, 1], weights: [],
      control_points: [{ x: 0, y: 0 }, { x: 2, y: 2 }, { x: 4, y: 2 }, { x: 6, y: 0 }],
      layer: 0, net: "CL1", is_active: true }],
    curves: [{ start: { x: 6, y: 0 }, mid: { x: 8, y: -1 }, end: { x: 6, y: -2 },
      layer: 1, net: "CL1", is_active: true }],
  }],
};

test("sensor curves stay curved in inline and expanded previews", async ({ page }) => {
  await page.route("**/src/lib/ipc/sensor.ts", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export async function generateSensorGeometry() { return ${JSON.stringify(geometry)}; }
      export async function exportSensorDxf() {}
      export async function writeSensorToBoard() {}`,
  }));
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "New coil file", exact: true }).click();
  await page.getByRole("dialog", { name: "New coil file" }).getByRole("button", { name: /^Sensor coil/ }).click();
  const preview = page.locator('section[aria-labelledby="sensor-preview-title"]');
  await expect(preview.locator("line")).toHaveCount(0);
  await expect(preview.getByRole("img").locator("path")).toHaveCount(2);
  await expect(preview.locator('path[d*=" C "]')).toHaveCount(1);
  await expect(preview.locator('path[d*=" A "]')).toHaveCount(1);
  await preview.getByRole("button", { name: "Expand sensor preview" }).click();
  const modal = page.getByRole("dialog", { name: "Induction sensor preview", exact: true });
  await expect(modal.getByRole("img").locator("path")).toHaveCount(2);
  await modal.getByRole("checkbox", { name: "Show layer 0" }).uncheck();
  await expect(modal.locator('path[d*=" C "]')).toHaveCount(0);
  await expect(modal.locator('path[d*=" A "]')).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();
  await expect(preview.getByRole("img").locator("path")).toHaveCount(1);
});

test("CAD import retains spline-only geometry in its preview and the motor designer", async ({ page }) => {
  const cad: CadGeometry = {
    routing: { format_version: 2, segments: [], curves: [], vias: [], splines: geometry.nets[0].splines },
    layer_z_mm: [-1.6, 0], trace_width_mm: 0.15,
  };
  await page.route("**/src/lib/ipc/dxf.ts", async (route) => {
    const response = await route.fetch();
    const body = (await response.text())
      .replace("export async function pickCadDxfPath() {", 'export async function pickCadDxfPath() { return "/sensor.dxf";')
      .replace("export async function importCadDxf(", "export async function importCadDxfOriginal(");
    await route.fulfill({ response, body: `${body}\nexport async function importCadDxf() { return ${JSON.stringify({ geometry: cad, warnings: [] })}; }` });
  });
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Routing source", exact: true }).click();
  await page.getByRole("option", { name: "Load design from file…" }).click();
  const dialog = page.getByRole("dialog", { name: "Import CAD", exact: true });
  await dialog.getByRole("button", { name: "Choose DXF…" }).click();
  await expect(dialog.locator('path[d*=" C "]')).toHaveCount(1);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await expect(dialog).toBeHidden();
  // The canvas counts spline paths as visible elements without storing a
  // tessellated copy in the imported CAD model.
  await expect(page.locator("canvas[data-segments]")).toHaveAttribute("data-segments", "1");
  await expect(page.getByRole("group", { name: "Imported CAD pattern", exact: true })).toBeVisible();
});
