import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

async function selectDesignType(page: Page, name: string) {
  await page.getByRole("button", { name: "Design type", exact: true }).click();
  await page.getByRole("option", { name, exact: true }).click();
}

test("motor magnet settings stay visible when clicking the section heading", async ({ page }) => {
  await gotoDesignApp(page);
  const magnets = page.getByRole("region", { name: "Magnets", exact: true });
  await expect(magnets.locator("details, summary")).toHaveCount(0);
  await magnets.getByRole("heading", { name: "Magnets", exact: true }).click();
  await expect(magnets.getByLabel("Magnet count", { exact: true })).toBeVisible();
  await expect(magnets.getByLabel("X Length (mm), magnet length along the travel axis")).toBeVisible();
  await expect(magnets.getByLabel("Y Width (mm), magnet width across the stator")).toBeVisible();
  await expect(magnets.getByLabel("Z Thickness (mm), magnetisation-axis thickness")).toBeVisible();
  await expect(magnets.getByRole("button", { name: "Magnet grade", exact: true })).toBeVisible();
});

test("sensor is a design type whose full workflow lives in the Design tab", async ({ page }) => {
  await gotoDesignApp(page);
  await expect(page.locator("#tab-sensor")).toHaveCount(0);
  // Export moved to the native File menu, so it is no longer a workflow tab.
  await expect(page.getByRole("tab", { name: "Export" })).toHaveCount(0);
  await selectDesignType(page, "Sensor");
  await expect(page.getByRole("tab", { name: /^Simulate/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sensor dimensions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Prepare 3D DXF" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Preview and export" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Write tracks and vias" })).toHaveCount(0);
  // Sensor IPC intentionally requires Tauri rather than browser mock geometry.
  await expect(page.getByRole("alert")).toContainText("require the desktop app");
  await page.locator("#sensor-wavelength").fill("48");
  await page.locator("#sensor-wavelength").press("Enter");
  await selectDesignType(page, "Motor coil");
  await expect(page.getByRole("tab", { name: /^Simulate/ })).toBeVisible();
  await selectDesignType(page, "Sensor");
  await expect(page.locator("#sensor-wavelength")).toHaveValue("48");
});

test("motor trace and via settings are editable and retained across design types", async ({ page }) => {
  await gotoDesignApp(page);
  for (const [id, value] of [
    ["motor-trace-width", "0.2"],
    ["motor-trace-gap", "0.15"],
    ["motor-via-drill", "0.3"],
    ["motor-via-annular-ring", "0.15"],
  ]) {
    await page.locator(`#${id}`).fill(value);
    await page.locator(`#${id}`).press("Enter");
  }
  await expect(page.getByText("Via diameter: 0.600 mm.", { exact: false })).toBeVisible();
  await selectDesignType(page, "Sensor");
  await selectDesignType(page, "Motor coil");
  await expect(page.locator("#motor-trace-width")).toHaveValue("0.2");
  await expect(page.locator("#motor-via-drill")).toHaveValue("0.3");
});

test("sensor preview supports layer visibility, zoom, pan and reset", async ({ page }) => {
  // Stub the native geometry response, keeping the actual preview and gestures.
  await page.route("**/src/lib/ipc/sensor.ts", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export async function generateSensorGeometry() {
      return { board_bounds_mm: [0, -5, 40, 5], terminal_markers: [], nets: [{
        name: 'CL1', trace_width_mm: 0.15, via_size_mm: 0.6, vias: [],
        segments: [
          { start: {x: 0, y: 0}, end: {x: 40, y: 0}, layer: 0 },
          { start: {x: 0, y: 1}, end: {x: 40, y: 1}, layer: 1 }
        ]
      }] };
    }
    export async function exportSensorDxf() {}
    export async function writeSensorToBoard() {}`,
  }));
  await gotoDesignApp(page);
  await selectDesignType(page, "Sensor");
  const preview = page.locator('section[aria-labelledby="sensor-preview-title"]');
  await expect(preview.locator("line")).toHaveCount(2);
  await preview.getByRole("checkbox", { name: "Show layer 1" }).uncheck();
  await expect(preview.locator("line")).toHaveCount(1);
  await preview.getByRole("checkbox", { name: "Show layer 1" }).check();
  await expect(preview.locator("line")).toHaveCount(2);
  const transform = preview.locator("svg > g");
  const initial = await transform.getAttribute("transform");
  for (const x of [24, 736]) {
    const frame = preview.getByRole("img");
    const bounds = (await frame.boundingBox())!;
    // MouseEvent coordinates are integer CSS pixels. Measure the anchor at
    // the actual dispatched cursor, not its unrounded virtual position.
    const clientX = Math.floor(bounds.x + x / 760 * bounds.width);
    const clientY = Math.floor(bounds.y + 24 / 260 * bounds.height);
    const vx = (clientX - bounds.x) / bounds.width * 760;
    const vy = (clientY - bounds.y) / bounds.height * 260;
    const anchorAt = async () => {
      const matrix = (await transform.getAttribute("transform"))!
        .slice(7, -1).split(" ").map(Number);
      return { x: (vx - matrix[4]) / matrix[0], y: (vy - matrix[5]) / matrix[3] };
    };
    const originalAnchor = await anchorAt();
    for (let i = 0; i < 8; i += 1) {
      await frame.evaluate((element, cursor) => {
        element.dispatchEvent(new WheelEvent("wheel", {
          ctrlKey: true, deltaY: -100, cancelable: true,
          clientX: cursor.clientX,
          clientY: cursor.clientY,
        }));
      }, { clientX, clientY });
      await expect(preview.getByRole("button", { name: "Reset zoom", exact: true }))
        .toHaveText(`${2 ** (i + 1)}×`);
      const anchor = await anchorAt();
      expect(anchor.x).toBeCloseTo(originalAnchor.x, 6);
      expect(anchor.y).toBeCloseTo(originalAnchor.y, 6);
    }
    await preview.getByRole("button", { name: "Reset zoom and pan" }).click();
    await expect(transform).toHaveAttribute("transform", initial!);
  }
  await preview.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(preview.getByRole("button", { name: "Reset zoom", exact: true })).toHaveText("1.5×");
  await expect(transform).not.toHaveAttribute("transform", initial!);
  await preview.getByRole("button", { name: "Reset zoom and pan" }).click();
  await expect(transform).toHaveAttribute("transform", initial!);
  const frame = preview.getByRole("img");
  const bounds = (await frame.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width / 2 + 40, bounds.y + bounds.height / 2 + 20, { steps: 5 });
  await page.mouse.up();
  await expect(transform).not.toHaveAttribute("transform", initial!);
  await preview.getByRole("button", { name: "Reset zoom and pan" }).click();
  await expect(transform).toHaveAttribute("transform", initial!);
});

test("switching from motor simulation to sensor opens sensor design", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/ }).click();
  await selectDesignType(page, "Sensor");
  await expect(page.getByRole("tab", { name: /^Design/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#sensor-wavelength")).toBeVisible();
});

test("routing source offers file import last and cancellation keeps the generator", async ({ page }) => {
  await gotoDesignApp(page);
  const source = page.getByRole("button", { name: "Routing source", exact: true });
  const originalSource = await source.textContent();
  await source.click();
  await expect(page.getByRole("option").last()).toHaveText("Load design from file…");
  await page.getByRole("option", { name: "Load design from file…" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(source).toHaveText(originalSource!);
});
