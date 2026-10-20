import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

async function selectPanel(page: import("@playwright/test").Page, name: string) {
  const trigger = page.getByRole("toolbar", { name: "Design side tools", exact: true }).getByRole("button", { name, exact: true });
  if (await trigger.getAttribute("aria-expanded") !== "true") await trigger.click();
}

test("Simulate opens four result tabs below the same live coil workspace", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const canvas = page.getByRole("region", { name: "Coil design workspace", exact: true }).locator("canvas");
  await expect.poll(async () => Number(await canvas.getAttribute("data-segments"))).toBeGreaterThan(0);
  await canvas.evaluate((el) => el.setAttribute("data-test-instance", "retained"));
  const before = (await canvas.boundingBox())!;
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await expect(dock).toBeVisible();
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute("data-test-instance", "retained");
  const preview = (await canvas.boundingBox())!;
  const results = (await dock.boundingBox())!;
  expect(preview.width).toBe(before.width);
  expect(preview.height).toBeLessThan(before.height);
  expect(preview.y + preview.height).toBeLessThanOrEqual(results.y);
  const status = page.getByRole("group", { name: "Preview status", exact: true });
  const statusBounds = (await status.boundingBox())!;
  for (const tab of await dock.getByRole("tab").all()) {
    const bounds = (await tab.boundingBox())!;
    const label = (await tab.locator("span").boundingBox())!;
    expect(Math.abs(bounds.y + bounds.height / 2 - label.y - label.height / 2)).toBeLessThanOrEqual(0.5);
  }
  expect(results.y + results.height).toBe(statusBounds.y);
  expect(statusBounds.y + statusBounds.height).toBe(page.viewportSize()!.height);
  expect(await page.getByRole("group", { name: "Preview status", exact: true }).count()).toBe(1);
  for (const name of ["Magnetic flux density", "Thrust vs. position", "Driver suitability", "Summary (live metrics)"]) {
    await dock.getByRole("tab", { name, exact: true }).click();
    await expect(dock.getByRole("tab", { name, exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(dock.getByRole("tabpanel", { name, exact: true })).toBeVisible();
  }
  await expect(dock.getByRole("spinbutton")).toHaveCount(0);
  await expect(dock.getByRole("combobox")).toHaveCount(0);
  await expect(dock.getByRole("heading", { name: "Live metrics", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("simulation-summary.png") });
  await dock.getByRole("tab", { name: "Thrust vs. position", exact: true }).click();
  await expect(dock.getByRole("img", { name: "Thrust sweep plot", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("simulation-thrust.png") });
  await expect(dock.getByRole("button", { name: "Close simulation panel", exact: true })).toHaveCount(0);
  const expandedHeight = (await dock.boundingBox())!.height;
  await dock.getByRole("button", { name: "Collapse simulation panel", exact: true }).click();
  await expect(dock).toBeVisible();
  await expect(dock.getByRole("img", { name: "Thrust sweep plot", exact: true })).toBeHidden();
  expect((await dock.boundingBox())!.height).toBeLessThan(64);
  await expect(dock.getByRole("separator", { name: "Resize simulation panel", exact: true })).toHaveCount(0);
  await expect(dock.locator('[role="tab"][aria-selected="true"]')).toHaveCount(0);
  const expand = dock.getByRole("button", { name: "Expand simulation panel", exact: true });
  const rowBounds = (await expand.locator("..").boundingBox())!;
  for (const tab of await dock.getByRole("tab").all()) {
    const label = (await tab.locator("span").boundingBox())!;
    expect(Math.abs(rowBounds.y + rowBounds.height / 2 - label.y - label.height / 2)).toBeLessThanOrEqual(0.5);
  }
  const collapsedBounds = (await dock.boundingBox())!;
  expect(Math.abs(collapsedBounds.height - rowBounds.height - 1)).toBeLessThanOrEqual(1);
  expect(Math.abs(rowBounds.y + rowBounds.height - (await status.boundingBox())!.y)).toBeLessThanOrEqual(1);
  const chevronBounds = (await expand.locator("svg").boundingBox())!;
  const buttonBounds = (await expand.boundingBox())!;
  expect(Math.abs(chevronBounds.x + chevronBounds.width / 2 - buttonBounds.x - buttonBounds.width / 2)).toBeLessThanOrEqual(1);
  expect(Math.abs(chevronBounds.y + chevronBounds.height / 2 - rowBounds.y - rowBounds.height / 2)).toBeLessThanOrEqual(1);
  await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
  await expect(dock.getByRole("tab", { name: "Thrust vs. position", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("simulation-collapsed.png") });
  await dock.getByRole("button", { name: "Expand simulation panel", exact: true }).click();
  expect((await dock.boundingBox())!.height).toBe(expandedHeight);
  await expect(dock.getByRole("img", { name: "Thrust sweep plot", exact: true })).toBeVisible();
  await expect(dock.getByRole("tab", { name: "Thrust vs. position", exact: true })).toHaveAttribute("aria-selected", "true");
  expect((await status.boundingBox())!.y + (await status.boundingBox())!.height).toBe(page.viewportSize()!.height);
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(dock).toBeHidden();
  await expect(page.getByRole("tab", { name: /^Design/i })).toHaveAttribute("aria-selected", "true");
  await expect(canvas).toHaveAttribute("data-test-instance", "retained");
});

test("the results dock resizes with pointer and keyboard and remembers its height", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  const handle = dock.getByRole("separator", { name: "Resize simulation panel", exact: true });
  const initial = (await dock.boundingBox())!.height;
  const grip = (await handle.boundingBox())!;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2 - 70, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await dock.boundingBox())!.height).toBe(initial + 70);
  await handle.press("ArrowDown");
  await expect.poll(async () => (await dock.boundingBox())!.height).toBe(initial + 46);
  await dock.getByRole("button", { name: "Collapse simulation panel", exact: true }).click();
  await expect(dock.locator('[role="tab"][aria-selected="true"]')).toHaveCount(0);
  await dock.getByRole("tab", { name: "Summary (live metrics)", exact: true }).click();
  await expect(dock.getByRole("heading", { name: "Live metrics", exact: true })).toBeVisible();
  await expect(dock.getByRole("tab", { name: "Summary (live metrics)", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(dock.getByRole("separator", { name: "Resize simulation panel", exact: true })).toBeVisible();
  expect((await dock.boundingBox())!.height).toBe(initial + 46);
  await page.getByRole("tab", { name: /^Design/i }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect.poll(async () => (await dock.boundingBox())!.height).toBe(initial + 46);
  await handle.press("End");
  await expect.poll(async () => Number(await handle.getAttribute("aria-valuenow"))).toBe(Number(await handle.getAttribute("aria-valuemax")));
  const preview = page.getByRole("region", { name: "Coil design workspace", exact: true });
  expect((await preview.boundingBox())!.height).toBeGreaterThanOrEqual(160);
  await handle.press("Home");
  expect((await dock.boundingBox())!.height).toBe(Number(await handle.getAttribute("aria-valuemin")));
});

test("operating and thermal settings live in the left target panel and update live metrics", async ({ page }) => {
  await gotoDesignApp(page);
  await selectPanel(page, "Drive & force targets");
  const targets = page.getByRole("dialog", { name: "Drive & force targets", exact: true });
  for (const name of ["Phase current (A)", "Continuous target force (N)", "Peak target force (N)", "Friction estimate (N)", "Bus voltage (V)", "PWM frequency (kHz)", "Target speed (m/s)", "Ripple limit (% of phase current)", "Usable bus share (%)", "Allowed trace temperature rise (°C)", "Winding temperature (°C)"]) {
    await expect(targets.getByRole("spinbutton", { name, exact: true })).toBeVisible();
  }
  const voltage = targets.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12");
  await voltage.press("Enter");
  await targets.getByRole("spinbutton", { name: "Winding temperature (°C)", exact: true }).fill("60");
  await targets.getByRole("spinbutton", { name: "Winding temperature (°C)", exact: true }).press("Enter");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(targets).toBeVisible();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await dock.getByRole("tab", { name: "Summary (live metrics)", exact: true }).click();
  const mean = dock.getByText("Mean thrust", { exact: true }).locator("..").locator(".font-mono");
  await expect(mean).not.toContainText("—");
  const previous = await mean.textContent();
  const current = targets.getByRole("spinbutton", { name: "Phase current (A)", exact: true });
  const initialCurrent = Number(await current.inputValue());
  await current.fill(String(initialCurrent * 2));
  await current.press("Enter");
  await expect(mean).not.toHaveText(previous!);
  await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
  await selectPanel(page, "Driver settings");
  await expect(targets).toHaveCount(0);
  const driver = page.getByRole("dialog", { name: "Preview driver settings", exact: true });
  await expect(driver.getByRole("spinbutton", { name: "Series inductor per phase (µH)", exact: true })).toBeVisible();
  await expect(driver.getByRole("combobox", { name: "Driver to evaluate", exact: true })).toBeVisible();
  await expect(driver.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true })).toHaveCount(0);
  await selectPanel(page, "Drive & force targets");
  await expect(voltage).toHaveValue("12");
  await expect(targets.getByRole("spinbutton", { name: "Winding temperature (°C)", exact: true })).toHaveValue("60");
});

test("copper weights and via plating belong to Routing and persist across panels", async ({ page }) => {
  await gotoDesignApp(page);
  await selectPanel(page, "Routing");
  const routing = page.getByRole("dialog", { name: "Routing", exact: true });
  await routing.getByRole("combobox", { name: "Outer layer copper weight", exact: true }).selectOption("2");
  await routing.getByRole("combobox", { name: "Inner layer copper weight", exact: true }).selectOption("0.5");
  const plating = routing.getByRole("spinbutton", { name: "Via plating thickness (µm)", exact: true });
  await plating.fill("35");
  await plating.press("Enter");
  await expect(routing.getByRole("spinbutton", { name: "Winding temperature (°C)", exact: true })).toHaveCount(0);
  await selectPanel(page, "Driver settings");
  const driver = page.getByRole("dialog", { name: "Preview driver settings", exact: true });
  await expect(driver.getByRole("combobox", { name: "Outer layer copper weight", exact: true })).toHaveCount(0);
  await selectPanel(page, "Routing");
  await expect(routing.getByRole("combobox", { name: "Outer layer copper weight", exact: true })).toHaveValue("2");
  await expect(routing.getByRole("combobox", { name: "Inner layer copper weight", exact: true })).toHaveValue("0.5");
  await expect(plating).toHaveValue("35");
});

test("driver results update from the target panel even when the thrust sweep fails", async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      export async function evaluateForceSweep() { throw new Error('Test sweep failure'); }`,
  }));
  await gotoDesignApp(page);
  await selectPanel(page, "Routing");
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await dock.getByRole("tab", { name: "Driver suitability", exact: true }).click();
  await expect(dock.getByRole("alert").filter({ hasText: "Test sweep failure" })).toBeVisible();
  const results = dock.getByRole("region", { name: "Driver suitability", exact: true });
  await expect(results).toContainText("at 5.0 V");
  await selectPanel(page, "Drive & force targets");
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12");
  await voltage.press("Enter");
  await expect(results).toContainText("at 12.0 V");
  await expect(results).toContainText("10.20 V usable");
  await expect(page.getByRole("region", { name: "Coil design workspace", exact: true })).toBeVisible();
});

test("touch dragging the resize handle changes the dock height", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 1 });
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  const height = (await dock.boundingBox())!.height;
  const handle = (await dock.getByRole("separator", { name: "Resize simulation panel", exact: true }).boundingBox())!;
  const touch = { id: 1, x: handle.x + handle.width / 2, y: handle.y + handle.height / 2 };
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [touch] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ ...touch, y: touch.y - 50 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect.poll(async () => (await dock.boundingBox())!.height).toBe(height + 50);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("winding connection warnings open Routing without hiding the results dock", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await dock.getByRole("tab", { name: "Driver suitability", exact: true }).click();
  await dock.getByRole("button", { name: "Change winding connection", exact: true }).click();
  await expect(dock).toBeVisible();
  await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
  const routing = page.getByRole("dialog", { name: "Routing", exact: true });
  await routing.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await expect(dock.getByRole("list", { name: "Driver checks", exact: true })).toBeVisible();
  await expect(dock.getByText(/Driver analysis failed:/)).toHaveCount(0);
});

test("mobile keeps the preview, rails and resizable results inside the viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const dock = page.getByRole("region", { name: "Simulation results", exact: true });
  await expect(page.getByRole("region", { name: "Coil design workspace", exact: true })).toBeVisible();
  const handle = dock.getByRole("separator", { name: "Resize simulation panel", exact: true });
  await handle.press("End");
  await selectPanel(page, "Drive & force targets");
  const targets = page.getByRole("dialog", { name: "Drive & force targets", exact: true });
  const scroll = targets.locator("[data-scroll-area-viewport]");
  expect(await scroll.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await scroll.evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(targets.getByRole("spinbutton", { name: "Allowed trace temperature rise (°C)", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBe(844);
  const statusBounds = (await page.getByRole("group", { name: "Preview status", exact: true }).boundingBox())!;
  expect(statusBounds.y + statusBounds.height).toBe(844);
  await page.screenshot({ path: testInfo.outputPath("simulation-mobile.png") });
  await dock.getByRole("button", { name: "Collapse simulation panel", exact: true }).click();
  await expect(dock.getByRole("separator", { name: "Resize simulation panel", exact: true })).toHaveCount(0);
  await expect(dock.locator('[role="tab"][aria-selected="true"]')).toHaveCount(0);
  const expand = dock.getByRole("button", { name: "Expand simulation panel", exact: true });
  const row = (await expand.locator("..").boundingBox())!;
  const icon = (await expand.locator("svg").boundingBox())!;
  expect(Math.abs(row.y + row.height / 2 - icon.y - icon.height / 2)).toBeLessThanOrEqual(1);
  expect(Math.abs(row.y + row.height - (await page.getByRole("group", { name: "Preview status", exact: true }).boundingBox())!.y)).toBeLessThanOrEqual(1);
  await dock.getByRole("tab", { name: "Driver suitability", exact: true }).click();
  await expect(dock.getByRole("tab", { name: "Driver suitability", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(dock.getByRole("region", { name: "Driver suitability", exact: true })).toBeVisible();
});
