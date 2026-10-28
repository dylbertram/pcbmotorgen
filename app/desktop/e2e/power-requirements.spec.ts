import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { gotoDesignApp } from "./helpers";

async function openPower(page: Page) {
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: "Power requirements", exact: true }).click();
  return page.getByRole("region", { name: "Power requirements", exact: true });
}

test("power tab discloses demo data and downloads a report without fabricated waveforms", async ({ page }) => {
  await gotoDesignApp(page);
  const panel = await openPower(page);
  await expect(panel).toContainText("Demo mode");
  await expect(panel.getByRole("heading", { level: 3 })).toHaveCount(8);
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeDisabled();
  await expect(panel.getByRole("button", { name: "Phase electrical CSV", exact: true })).toBeDisabled();
  for (const [button, filename] of [["Download report", "power-requirements-report.md"], ["Requirements CSV", "power-requirements-summary.csv"], ["Model snapshot JSON", "power-requirements-model.json"]]) {
    const downloaded = page.waitForEvent("download");
    await panel.getByRole("button", { name: button, exact: true }).click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe(filename);
    const content = await readFile((await download.path())!, "utf8");
    expect(content).toContain("Unknown");
    if (filename.endsWith(".json")) {
      const snapshot = JSON.parse(content);
      expect(snapshot.results_provenance).toBe("demo_results_withheld");
      expect(snapshot.drive).toBeNull();
      expect(snapshot.sweep).toBeNull();
    }
  }
  await page.getByRole("tab", { name: "Magnetic flux density", exact: true }).click();
  await expect(page.locator('[data-dock-panel="flux"]')).toBeVisible();
});

// These tests inject synthetic DTOs at the transport boundary. They verify
// report state and native save flows, not the Rust solver or native dialogs.
async function syntheticResults(page: Page) {
  await page.route(/\/src\/DocumentEditor\.svelte(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const original = await response.text();
    expect(original).toContain("native: isTauriAvailable()");
    await route.fulfill({ response, body: original.replace("native: isTauriAvailable()", "native: true") });
  });
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      import { mockDriveAnalysis, mockForceSweep } from '/src/lib/ipc/mocks.ts';
      export async function evaluateForceSweep(config) {
        if (window.__failForce) throw new Error('Synthetic force failure');
        return mockForceSweep(config);
      }
      export async function analyzeDrive(config, settings, kf) {
        if (window.__failDrive) throw new Error('Synthetic drive failure');
        if (window.__holdDrive) await new Promise((resolve, reject) => {
          window.__driveWaiting = true;
          window.addEventListener('release-drive', () => reject(new Error('Synthetic drive failure')), {once: true});
        });
        return mockDriveAnalysis(config, settings, kf);
      }`,
  }));
  await page.route(/\/src\/lib\/files\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function saveTextToFile(content, fileName, extensions) {
      if (window.__failSave) throw new Error('Synthetic write failure');
      if (window.__cancelSave) return null;
      window.__savedPower = { content, fileName, extensions };
      return '/exports/' + fileName;
    }`,
  }));
}

test("current results export; pending and failed updates never export retained driver values", async ({ page }) => {
  await syntheticResults(page);
  await gotoDesignApp(page);
  const panel = await openPower(page);
  const electrical = panel.getByRole("button", { name: "Phase electrical CSV", exact: true });
  await expect(electrical).toBeEnabled();
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeEnabled();
  await electrical.click();
  await expect(panel.getByRole("status")).toContainText("Saved /exports/power-requirements-electrical.csv");
  expect(await page.evaluate(() => (window as any).__savedPower.content)).toContain('"resistance_hot_ohm"');

  await page.evaluate(() => { (window as any).__holdDrive = true; });
  await page.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12");
  await voltage.press("Enter");
  await page.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  await page.getByRole("tab", { name: "Power requirements", exact: true }).click();
  await expect(electrical).toBeDisabled();
  await expect(panel.locator("dl > div").filter({ has: page.getByText("Winding resistance per phase", { exact: true }) })).toContainText("Unknown");
  await expect.poll(() => page.evaluate(() => (window as any).__driveWaiting)).toBe(true);
  await page.evaluate(() => {
    (window as any).__failDrive = true;
    (window as any).__holdDrive = false;
    window.dispatchEvent(new Event("release-drive"));
  });
  await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
  const snapshot = JSON.parse(await page.evaluate(() => (window as any).__savedPower.content));
  expect(snapshot.config.supply_voltage_v).toBe(12);
  expect(snapshot.drive).toBeNull();
  expect(snapshot.sections[5].rows.find((row: any) => row.label === "Peak supply power during a move").value).toBe("Unknown");
});

test("failed force updates remove force exports and do not supply an old force constant", async ({ page }) => {
  await syntheticResults(page);
  await gotoDesignApp(page);
  const panel = await openPower(page);
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeEnabled();
  await page.evaluate(() => { (window as any).__failForce = true; });
  await page.getByRole("tab", { name: /^Design/i }).click();
  await page.getByRole("button", { name: "Magnets", exact: true }).click();
  await page.locator("input#magnet-count").fill("6");
  await page.locator("input#magnet-count").press("Enter");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(panel.getByRole("button", { name: "Force sweep CSV", exact: true })).toBeDisabled();
  await expect(page.getByRole("alert").filter({ hasText: "Computation error: Synthetic force failure" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Phase electrical CSV", exact: true })).toBeEnabled();
  // Sweep completion schedules another driver check. Wait for that check's
  // published snapshot rather than racing its legitimate pending/null state.
  await expect(async () => {
    await panel.getByRole("button", { name: "Model snapshot JSON", exact: true }).click();
    const snapshot = JSON.parse(await page.evaluate(() => (window as any).__savedPower.content));
    expect(snapshot.config.magnet_count).toBe(6);
    expect(snapshot.sweep).toBeNull();
    expect(snapshot.drive).not.toBeNull();
    expect(snapshot.drive.thrust_constant_n_per_a).toBeNull();
  }).toPass();

  await page.evaluate(() => { (window as any).__failSave = true; });
  await panel.getByRole("button", { name: "Download report", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Synthetic write failure");
  await page.evaluate(() => { (window as any).__failSave = false; (window as any).__cancelSave = true; });
  await panel.getByRole("button", { name: "Download report", exact: true }).click();
  await expect(panel.getByRole("alert")).toHaveCount(0);
  await expect(panel.getByRole("status")).toHaveCount(0);
});
