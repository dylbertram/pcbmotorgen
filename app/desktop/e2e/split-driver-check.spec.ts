import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp, openDriverChecks, selectDesignPanel, simulationDock } from "./helpers";

async function nativeMenu(page: Page) {
  // This transport tests the real App -> DocumentEditor command route. Native
  // item IDs/labels and event validation have separate Rust/TS coverage.
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      export async function bindProjectMenuActions(handlers) {
        const simulate = e => handlers.simulate?.(e.detail);
        window.addEventListener('test-simulate', simulate);
        const close = () => handlers.closeFile?.();
        window.addEventListener('test-close-file', close);
        return () => { window.removeEventListener('test-simulate', simulate); window.removeEventListener('test-close-file', close); };
      }`,
  }));
}

test("unified workspace, min/max links and consistently underlined Advanced", async ({ page }) => {
  await gotoDesignApp(page);
  const dock = simulationDock(page);
  await expect(page.getByRole("tab", { name: /^(Design|Simulate)$/i })).toHaveCount(0);
  await expect(dock).toBeVisible();
  await expect(dock.getByRole("tab")).toHaveText(["Move & power", "Force", "Fields", "Advanced"]);
  const toolbar = page.getByRole("toolbar", { name: "Coil preview tools", exact: true });
  await expect(toolbar.getByRole("button", { name: /^Design rule check:/ })).toBeVisible();
  await expect(toolbar.getByText("ready", { exact: true })).toBeVisible();
  const move = page.getByRole("region", { name: "Move and power", exact: true });
  await expect(move.getByRole("button", { name: "Full travel", exact: true })).toHaveCount(0);
  const from = move.getByRole("spinbutton", { name: "Move start in millimetres", exact: true });
  const to = move.getByRole("spinbutton", { name: "Move end in millimetres", exact: true });
  const max = await to.inputValue();
  await from.fill("10");
  await to.fill("20");
  await move.getByRole("button", { name: "Set move start to minimum", exact: true }).click();
  await expect(from).toHaveValue("0");
  await expect(to).toHaveValue("20");
  await move.getByRole("button", { name: "Set move end to maximum", exact: true }).click();
  await expect(to).toHaveValue(max);
  await expect(move.locator("header")).toContainText("mass and friction");
  await expect(move.locator("p").filter({ hasText: /^Choose Calculate/ })).toHaveCount(0);
  for (const name of ["Move & power", "Force", "Fields", "Advanced"]) {
    const tab = dock.getByRole("tab", { name, exact: true });
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    const underline = await tab.evaluate(el => getComputedStyle(el, "::after").backgroundColor);
    expect(underline).not.toBe("rgba(0, 0, 0, 0)");
  }
  await expect(dock.getByRole("button", { name: /Back to/ })).toHaveCount(0);
});

test("driver check is a resizable closable split document, not nested Force content", async ({ page }, info) => {
  await gotoDesignApp(page);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const canvas = workspace.getByTestId("coil-annotations");
  await canvas.evaluate(el => el.setAttribute("data-instance", "retained"));
  await openDriverChecks(page);
  const driver = page.getByTestId("driver-check-document");
  const dock = simulationDock(page);
  await expect(dock.getByText("Friction budget", { exact: true })).toHaveCount(0);
  await expect(dock.getByText("Stack height", { exact: true })).toHaveCount(0);
  await expect(dock.getByText("Net of friction:", { exact: true })).toHaveCount(0);
  await expect(dock.getByRole("region", { name: "Force", exact: true }).locator("details")).toHaveCount(0);
  await expect(driver.getByRole("region", { name: "Routed copper measurements", exact: true })).toBeVisible();
  await expect(driver.getByRole("columnheader", { name: "Strands", exact: true })).toHaveCount(0);
  await expect(canvas).toHaveAttribute("data-instance", "retained");
  const left = (await workspace.boundingBox())!, right = (await driver.boundingBox())!;
  expect(right.x).toBeGreaterThanOrEqual(left.x + left.width);
  expect(Math.abs(right.y - left.y)).toBeLessThanOrEqual(1);
  const analysisHeader = page.getByRole("navigation", { name: "Analysis editor group", exact: true });
  expect((await analysisHeader.boundingBox())!.x).toBe(right.x);
  const handle = page.getByRole("separator", { name: "Resize editor groups", exact: true });
  const width = left.width;
  await handle.press("ArrowLeft");
  await expect.poll(async () => (await workspace.boundingBox())!.width).toBeLessThan(width);
  const grip = (await handle.boundingBox())!;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x + grip.width / 2 - 40, grip.y + grip.height / 2, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await workspace.boundingBox())!.width).toBeLessThan(width - 40);
  expect((await analysisHeader.boundingBox())!.x).toBe((await driver.boundingBox())!.x);
  await page.screenshot({ path: info.outputPath("split-driver-check.png") });
  await page.getByRole("button", { name: "Close driver check", exact: true }).click();
  await expect(driver).toHaveCount(0);
  await expect(canvas).toHaveAttribute("data-instance", "retained");
  expect((await workspace.boundingBox())!.width).toBeGreaterThan(width);
  await expect(dock).toBeVisible();
  await openDriverChecks(page);
  await expect(page.getByRole("tab", { name: /^Driver check/ })).toHaveCount(1);
  await openDriverChecks(page);
  await expect(page.getByRole("tab", { name: /^Driver check/ })).toHaveCount(1);
});

test("source edits invalidate the linked driver result and reopening keeps its source", async ({ page }) => {
  await gotoDesignApp(page);
  await openDriverChecks(page);
  const driver = page.getByTestId("driver-check-document");
  await expect(driver).toContainText("5.0 V");
  await selectDesignPanel(page, "Drive & force targets");
  const voltage = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await voltage.fill("12");
  await voltage.press("Enter");
  await expect(driver).toContainText("12.0 V");
  await expect(driver).not.toContainText("5.0 V bus");
});

test("native Simulate commands select views and open the same driver document", async ({ page }) => {
  await nativeMenu(page);
  await gotoDesignApp(page);
  for (const [id, label] of [["force", "Force"], ["fields", "Fields"], ["advanced", "Advanced"], ["move", "Move & power"]]) {
    await page.evaluate(id => window.dispatchEvent(new CustomEvent("test-simulate", { detail: id })), id);
    await expect(simulationDock(page).getByRole("tab", { name: label, exact: true })).toHaveAttribute("aria-selected", "true");
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-simulate", { detail: "driver" })));
  await expect(page.getByTestId("driver-check-document")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-close-file")));
  await expect(page.getByTestId("driver-check-document")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Open files" }).getByRole("tab")).toHaveCount(1);
});

test("each source retains its own analysis group and simulation view", async ({ page }) => {
  await gotoDesignApp(page);
  await openDriverChecks(page);
  const handle = page.getByRole("separator", { name: "Resize editor groups", exact: true });
  await handle.press("ArrowLeft");
  const percent = await handle.getAttribute("aria-valuenow");
  const files = page.getByRole("navigation", { name: "Open files", exact: true });
  const first = files.getByRole("tab").first();
  const firstName = (await first.innerText()).replace(/^M\s*/, "").replace(/●/g, "").trim();
  await page.getByRole("button", { name: "New coil file", exact: true }).click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
  await expect(page.getByTestId("driver-check-document")).toHaveCount(0);
  await expect(simulationDock(page).getByRole("tab", { name: "Move & power", exact: true })).toHaveAttribute("aria-selected", "true");
  await openDriverChecks(page);
  const secondName = (await files.getByRole("tab").nth(1).innerText()).replace(/^M\s*/, "").replace(/●/g, "").trim();
  await expect(page.getByTestId("driver-check-document")).toContainText(secondName);
  await page.getByRole("button", { name: "Close driver check", exact: true }).click();
  await first.click();
  await expect(page.getByTestId("driver-check-document")).toContainText(firstName);
  await expect(handle).toHaveAttribute("aria-valuenow", percent!);
  await expect(simulationDock(page).getByRole("tab", { name: "Force", exact: true })).toHaveAttribute("aria-selected", "true");
  await files.getByRole("tab").nth(1).click();
  await expect(page.getByTestId("driver-check-document")).toHaveCount(0);
});
