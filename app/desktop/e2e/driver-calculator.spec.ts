import { expect, test } from "@playwright/test";
import { emptyDriverInput } from "../src/lib/driver/driverCalculator";

test("screens back-EMF with measured Ke, loaded limits and missing constants", async ({ page }) => {
  await page.goto("/?tool=driver-calculator");
  await page.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true }).fill("2");
  await page.getByRole("spinbutton", { name: "Synchronous winding inductance (µH)", exact: true }).fill("100");
  await page.getByRole("spinbutton", { name: "Target speed (m/s)", exact: true }).fill("5");
  const assessment = page.getByRole("region", { name: "Back-EMF assessment", exact: true });
  const table = page.getByRole("table", { name: "Driver checks", exact: true });
  const emf = table.getByRole("row").filter({ hasText: "Open-circuit back-EMF" });
  const loaded = table.getByRole("row").filter({ hasText: "Voltage at target speed" });
  await expect(emf).toContainText("Not evaluated");
  const ke = page.getByRole("spinbutton", { name: "Phase-peak back-EMF constant, optional (V·s/m)", exact: true });
  await ke.fill("1");
  await expect(assessment).toContainText("entered phase-peak constant");
  await expect(emf).toContainText("Pass");
  await expect(loaded).toContainText("Not evaluated");
  await page.getByRole("spinbutton", { name: "Electrical period, optional (mm)", exact: true }).fill("12");
  await expect(loaded).toContainText("Fail");
  await page.getByRole("spinbutton", { name: "Target speed (m/s)", exact: true }).fill("10");
  await expect(emf).toContainText("Fail");
  await ke.fill("");
  await expect(emf).toContainText("Not evaluated");
  await page.getByRole("spinbutton", { name: "Force constant, optional (N/A)", exact: true }).fill("1.5");
  await expect(assessment).toContainText("estimated from force constant");
  await expect(emf).toContainText("Fail");
  await ke.fill("-1");
  await expect(assessment).toHaveCount(0);
  await expect(table).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText("Phase-peak back-EMF constant must be blank or positive");
});

test("exports the current calculation and handles save cancellation and failure", async ({ page }) => {
  await page.route(/\/src\/lib\/files\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function saveTextToFile(content, filename, extensions) {
      window.__savedExport = { content, filename, extensions };
      if (window.__saveMode === 'error') throw new Error('Disk full');
      return window.__saveMode === 'cancel' ? null : '/exports/' + filename;
    }`,
  }));
  await page.goto("/?tool=driver-calculator");
  await page.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true }).fill("2");
  await page.getByRole("spinbutton", { name: "Synchronous winding inductance (µH)", exact: true }).fill("100");
  await page.getByRole("spinbutton", { name: "Force constant, optional (N/A)", exact: true }).fill("1.5");
  await page.getByRole("spinbutton", { name: "Target speed (m/s)", exact: true }).fill("0.5");
  const json = page.getByRole("button", { name: "Export JSON", exact: true });
  const report = page.getByRole("button", { name: "Save report", exact: true });
  await json.click();
  await expect(page.getByRole("status")).toContainText("Saved /exports/driver-calculation.json");
  const saved = await page.evaluate(() => (window as any).__savedExport);
  expect(saved.extensions).toEqual(["json"]);
  expect(JSON.parse(saved.content).result).toMatchObject({ forceN: 1.5, phaseBackEmfV: .5, speedV: null });
  await page.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true }).fill("3");
  await report.click();
  await expect(page.getByRole("status")).toContainText("driver-calculation.html");
  const html = await page.evaluate(() => (window as any).__savedExport.content);
  expect(html).toContain("Hot phase resistance</td><td>3</td>");
  expect(html).toContain("Phase back-EMF");
  await page.evaluate(() => (window as any).__saveMode = "cancel");
  await json.click();
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(json).toBeEnabled();
  await page.evaluate(() => (window as any).__saveMode = "error");
  await report.click();
  await expect(page.getByRole("alert")).toContainText("Could not export driver results: Disk full");
  await expect(report).toBeEnabled();
  await page.evaluate(() => (window as any).__saveMode = "ok");
  await report.click();
  await expect(page.getByRole("status")).toContainText("driver-calculation.html");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

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

test("calculator panes scroll independently with the wheel and keyboard", async ({ page }) => {
  await page.goto("/?tool=driver-calculator");
  await page.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true }).fill("2");
  await page.getByRole("spinbutton", { name: "Synchronous winding inductance (µH)", exact: true }).fill("100");
  const calculator = page.getByRole("main", { name: "Driver calculator", exact: true });
  const left = page.getByRole("region", { name: "Calculator input pane", exact: true });
  const right = page.getByRole("region", { name: "Driver suitability checks", exact: true });
  for (const width of [1100, 1280]) {
    await page.setViewportSize({ width, height: 500 });
    for (const pane of [left, right]) {
      await pane.focus();
      await page.keyboard.press("Control+Home");
      await expect.poll(() => pane.evaluate(el => el.scrollTop)).toBe(0);
    }
    for (const [pane, other] of [[left, right], [right, left]]) {
      const otherOffset = await other.evaluate(el => el.scrollTop);
      const bounds = (await pane.boundingBox())!;
      await page.mouse.move(bounds.x + bounds.width - 20, bounds.y + 50);
      await page.mouse.wheel(0, 200);
      await expect.poll(() => pane.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
      await expect.poll(() => other.evaluate(el => el.scrollTop)).toBe(otherOffset);
      await pane.focus();
      await page.keyboard.press("Control+End");
      await expect.poll(() => pane.evaluate(el => Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop))).toBeLessThan(2);
      await page.mouse.wheel(0, 400);
      await expect.poll(() => other.evaluate(el => el.scrollTop)).toBe(otherOffset);
    }
    await expect(page.getByRole("spinbutton", { name: "Trace ampacity, optional (A)", exact: true })).toBeInViewport();
    expect(await calculator.evaluate(el => el.scrollTop)).toBe(0);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  }
});

test("stacked calculator content still scrolls at narrow widths", async ({ page }) => {
  await page.goto("/?tool=driver-calculator");
  const calculator = page.getByRole("main", { name: "Driver calculator", exact: true });
  for (const width of [390, 800]) {
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
    await expect(page.getByLabel("Calculator model limits").getByText(/Supply-current demand/)).toBeInViewport();
    await page.getByRole("spinbutton", { name: "Trace ampacity, optional (A)", exact: true }).scrollIntoViewIfNeeded();
    await expect(page.getByRole("spinbutton", { name: "Trace ampacity, optional (A)", exact: true })).toBeInViewport();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  }
});

test("a timed-out import cannot overwrite later calculator edits or a newer request", async ({ page }) => {
  await page.route(/\/src\/lib\/driver\/driverCalculatorWindow\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/driver/driverCalculatorWindow.ts?original';
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
