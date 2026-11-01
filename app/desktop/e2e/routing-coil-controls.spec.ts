import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gotoDesignApp, openDriverChecks, selectRoutingConnection } from "./helpers";

async function useNativeBraid(page: Page) {
  const directory = process.env.PCB_MOTOR_TERMINAL_FIXTURES;
  test.skip(!directory, "Export native braid payloads and set PCB_MOTOR_TERMINAL_FIXTURES to test automatic inference.");
  const coils = readFileSync(join(directory!, "generated-4-preview.json"), "utf8");
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original'; export async function generateCoils() { return ${coils}; }`,
  }));
}

test("source variants own the winding connection and preserve routing settings", async ({ page }) => {
  await gotoDesignApp(page);
  const polarity = page.getByRole("combobox", { name: "Star winding polarity", exact: true });
  await expect(polarity).toHaveValue("1");
  await polarity.selectOption("0");
  const strands = page.getByRole("spinbutton", { name: "Strands per period", exact: true });
  await strands.fill("5");
  await strands.press("Enter");
  await expect(page.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveCount(0);
  await selectRoutingConnection(page, "delta");
  await expect(strands).toHaveValue("5");
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil terminals", exact: true });
  await expect(panel.getByLabel("Generator winding connection")).toHaveText("Delta");
  await expect(panel.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveCount(0);
  await selectRoutingConnection(page, "star");
  await expect(polarity).toHaveValue("0");
  await polarity.selectOption("1");
  await expect(polarity).toHaveValue("1");
  await expect(strands).toHaveValue("5");
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await expect(panel.getByLabel("Generator winding connection")).toHaveText("Star (Wye)");
});

for (const mobile of [false, true]) {
  test(`coil ends allow position/layers switching and draft-only auto-selection ${mobile ? "on mobile" : "on desktop"}`, async ({ page }, testInfo) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await useNativeBraid(page);
    await gotoDesignApp(page);
    await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
    const panel = page.getByRole("dialog", { name: "Coil terminals", exact: true });
    const mode = page.getByRole("group", { name: "Position bar mode", exact: true });
    const position = mode.getByRole("button", { name: "position", exact: true });
    const layers = mode.getByRole("button", { name: "layers", exact: true });
    await expect(layers).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("slider", { name: "Preview layer", exact: true })).toBeVisible();
    await position.click();
    await expect(position).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("slider", { name: "Preview layer", exact: true })).toHaveCount(0);
    await panel.getByRole("button", { name: "Auto-select ends", exact: true }).click();
    await expect(panel.getByRole("button", { name: "Apply terminals", exact: true })).toBeEnabled();
    await expect(panel).toContainText("Automatic ends found for A");
    await expect(position).toHaveAttribute("aria-pressed", "true");
    await expect(panel.getByLabel("Generator winding connection")).toHaveText("Star (Wye)");
    await layers.click();
    const slider = page.getByRole("slider", { name: "Preview layer", exact: true });
    await slider.fill("2");
    await expect(slider).toHaveValue("2");
    if (mobile) {
      const barBounds = (await mode.boundingBox())!;
      const panelBounds = (await panel.boundingBox())!;
      expect(barBounds.y).toBeGreaterThanOrEqual(panelBounds.y + panelBounds.height);
      expect(barBounds.x).toBeGreaterThanOrEqual(44);
      expect(barBounds.x + barBounds.width).toBeLessThanOrEqual(346);
    }
    await page.screenshot({ path: testInfo.outputPath("coil-ends-layer-toggle.png") });
    await panel.getByRole("button", { name: "Cancel", exact: true }).click();
    // Cancelling the proposal has not frozen generated copper into an import.
    await expect(panel.getByLabel("Generator winding connection")).toBeVisible();
    await panel.getByRole("button", { name: "Close terminals panel", exact: true }).click();
    await expect(position).toHaveAttribute("aria-pressed", "true");
  });
}

test("frozen copper retains its editable winding selector", async ({ page }) => {
  await useNativeBraid(page);
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil terminals", exact: true });
  await panel.getByRole("button", { name: "Auto-select ends", exact: true }).click();
  await panel.getByRole("button", { name: "Apply terminals", exact: true }).click();
  const connection = panel.getByRole("combobox", { name: "Winding connection", exact: true });
  await expect(connection).toHaveValue("star");
  await connection.selectOption("delta");
  await expect(connection).toHaveValue("delta");
});

test("an undeclared generator's winding parameter moves to coil ends", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/routing\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/routing.ts?original';
      export async function listRoutingPatterns() { return [{ id: 'infinity-braid', display_name: 'Undeclared braid' }]; }`,
  }));
  await gotoDesignApp(page);
  await expect(page.getByRole("button", { name: "Routing source", exact: true })).toHaveText("Undeclared braid");
  await expect(page.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const connection = page.getByRole("combobox", { name: "Winding connection", exact: true });
  await expect(connection).toHaveValue("2");
  await connection.selectOption("1");
  await expect(connection).toHaveValue("1");
  await expect(page.getByLabel("Generator winding connection")).toHaveCount(0);
});

test("uploaded winding warnings lead to the editable connection in Coil ends", async ({ page }) => {
  await useNativeBraid(page);
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil terminals", exact: true });
  await panel.getByRole("button", { name: "Auto-select ends", exact: true }).click();
  await panel.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await panel.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("delta");
  await panel.getByRole("button", { name: "Close terminals panel", exact: true }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await openDriverChecks(page);
  await dock.getByRole("button", { name: "Change winding connection", exact: true }).click();
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveValue("delta");
  await expect(page.getByRole("dialog", { name: "Routing", exact: true })).toHaveCount(0);
  await expect(dock).toBeVisible();
});

test("failed automatic inference leaves generated copper live and offers manual selection", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil terminals", exact: true });
  // The browser's ordinary mock is disconnected, unlike the native fixtures.
  await panel.getByRole("button", { name: "Auto-select ends", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Select them manually");
  await expect(panel.getByRole("button", { name: "Apply terminals", exact: true })).toBeDisabled();
  await expect(panel.getByLabel("Generator winding connection")).toHaveText("Star (Wye)");
  await expect(panel.getByRole("button", { name: "Select driver end for coil A", exact: true })).toBeEnabled();
});

test("a generator with a fixed end type has a read-only connection", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/routing\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/routing.ts?original';
      export async function listRoutingPatterns() { return [{ id: 'infinity-braid', display_name: 'Fixed braid', end_type: {kind:'fixed',connection:'star'} }]; }
      export async function routingPatternParameters() { return []; }`,
  }));
  await gotoDesignApp(page);
  await expect(page.getByRole("button", { name: "Routing source", exact: true })).toHaveText("Fixed braid - Star (Wye)");
  await page.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await expect(page.getByLabel("Generator winding connection")).toHaveText("Star (Wye)");
  await expect(page.getByRole("combobox", { name: "Winding connection", exact: true })).toHaveCount(0);
});
