import { expect, test } from "@playwright/test";
import { emptyDriverInput } from "../src/lib/driverCalculator";

test("the standalone calculator works without a motor and clears invalid checks", async ({ page }, info) => {
  await page.goto("/?tool=driver-calculator");
  await expect(page.getByRole("heading", { name: "Driver calculator", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Driver checks", exact: true })).toHaveCount(0);
  const resistance = page.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true });
  await resistance.fill("2");
  await page.getByRole("spinbutton", { name: "Synchronous winding inductance (µH)", exact: true }).fill("100");
  const table = page.getByRole("table", { name: "Driver checks", exact: true });
  await expect(table).toBeVisible();
  const bus = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await bus.fill("24");
  const supply = table.getByRole("row").filter({ hasText: "Driver supply range" });
  await expect(supply).toContainText("Fail");
  await page.getByRole("combobox", { name: "Driver to evaluate", exact: true }).selectOption("DRV8316");
  await expect(supply).toContainText("Pass");
  await bus.fill(""); await expect(table).toHaveCount(0);
  await bus.fill("12"); await expect(table).toBeVisible();
  await page.getByRole("spinbutton", { name: "Target speed (m/s)", exact: true }).fill("0.5");
  await expect(table.getByRole("row").filter({ hasText: "Voltage at target speed" })).toContainText("Not evaluated");
  await page.getByRole("spinbutton", { name: "Force constant, optional (N/A)", exact: true }).fill("1.5");
  await page.getByRole("spinbutton", { name: "Electrical period, optional (mm)", exact: true }).fill("12");
  await expect(table.getByRole("row").filter({ hasText: "Voltage at target speed" })).not.toContainText("Not evaluated");
  await page.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("motor window is closed");
  await expect(resistance).toHaveValue("2");
  for (const width of [1100, 390]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await page.screenshot({ path: info.outputPath(`driver-calculator-${width}.png`) });
  }
});

test("calculator scrolls with the wheel and keyboard at desktop and narrow widths", async ({ page }) => {
  await page.goto("/?tool=driver-calculator");
  const calculator = page.getByRole("main", { name: "Driver calculator", exact: true });
  for (const width of [1100, 1280, 390]) {
    await page.setViewportSize({ width, height: 500 });
    await calculator.focus();
    await page.keyboard.press("Control+Home");
    await expect.poll(() => calculator.evaluate(el => el.scrollTop)).toBe(0);
    expect(await calculator.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    await page.mouse.move(width - 25, 200);
    await page.mouse.wheel(0, 350);
    await expect.poll(() => calculator.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await calculator.focus();
    await page.keyboard.press("Control+End");
    await expect.poll(() => calculator.evaluate(el => Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop))).toBeLessThan(2);
    await expect(page.getByRole("spinbutton", { name: "Trace ampacity, optional (A)", exact: true })).toBeInViewport();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  }
});

test("a timed-out import cannot overwrite later calculator edits or a newer request", async ({ page }) => {
  await page.route(/\/src\/lib\/driverCalculatorWindow\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/driverCalculatorWindow.ts?original';
      export async function calculatorSeed() { return null; }
      export async function requestDriverImport(id) { window.__importId = id; }
      export async function listenDriverImport(handler) { window.__importResult = handler; return () => {}; }`,
  }));
  await page.clock.install();
  await page.goto("/?tool=driver-calculator");
  const resistance = page.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true });
  await resistance.fill("2");
  await page.getByRole("button", { name: "Import active motor", exact: true }).click();
  const oldId = await page.evaluate(() => (window as any).__importId);
  await page.clock.runFor(8001);
  await expect(page.getByRole("alert")).toContainText("did not respond");
  await resistance.fill("3");
  const snapshot = { source: "Fixture motor", capturedAt: new Date().toISOString(), native: true, notes: [], input: { ...emptyDriverInput(), resistanceOhm: 7, inductanceH: 100e-6 } };
  await page.evaluate(response => (window as any).__importResult(response), { requestId: oldId, snapshot, error: null });
  await expect(resistance).toHaveValue("3");
  await page.getByRole("button", { name: "Import active motor", exact: true }).click();
  const newId = await page.evaluate(() => (window as any).__importId);
  expect(newId).not.toBe(oldId);
  await page.evaluate(response => (window as any).__importResult(response), { requestId: oldId, snapshot, error: null });
  await expect(resistance).toHaveValue("3");
  await page.evaluate(response => (window as any).__importResult(response), { requestId: newId, snapshot, error: null });
  await expect(resistance).toHaveValue("7");
});
