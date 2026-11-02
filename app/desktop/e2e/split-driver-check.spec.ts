import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel, simulationDock } from "./helpers";

async function splitRight(page: Page) {
  const tab = page.getByRole("navigation", { name: "Open files", exact: true }).getByRole("tab").first();
  await tab.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Split right", exact: true }).click();
  await expect(page.getByRole("region", { name: "Right editor group", exact: true })).toBeVisible();
}
async function newMotor(page: Page) {
  await page.getByRole("navigation", { name: "Open files", exact: true }).getByRole("button", { name: "New coil file", exact: true }).click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Motor coil/ }).click();
}

async function installMenuTransport(page: Page): Promise<void> {
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      export async function bindProjectMenuActions(handlers) {
        const listener = event => { if (event.detail === 'close') handlers.closeFile?.(); else handlers.simulate?.(event.detail); };
        window.addEventListener('test-menu', listener); return () => window.removeEventListener('test-menu', listener);
      }`,
  }));
}
test("unified workspace, min/max links and consistently underlined Advanced", async ({ page }) => {
  await gotoDesignApp(page);
  const dock = simulationDock(page);
  await expect(page.getByRole("tab", { name: /^(Design|Simulate)$/i })).toHaveCount(0);
  await expect(dock.getByRole("tab")).toHaveText(["Move & power", "Force", "Fields", "Advanced"]);
  const toolbar = page.getByRole("toolbar", { name: "Coil preview tools", exact: true });
  await expect(toolbar.getByRole("button", { name: /^Design rule check:/ })).toBeVisible();
  const move = page.getByRole("region", { name: "Move and power", exact: true });
  const from = move.getByRole("spinbutton", { name: "Move start in millimetres", exact: true });
  const to = move.getByRole("spinbutton", { name: "Move end in millimetres", exact: true });
  const max = await to.inputValue();
  await from.fill("10"); await to.fill("20");
  await move.getByRole("button", { name: "Set move start to minimum", exact: true }).click();
  await expect(from).toHaveValue("0"); await expect(to).toHaveValue("20");
  await move.getByRole("button", { name: "Set move end to maximum", exact: true }).click();
  await expect(to).toHaveValue(max);
  for (const name of ["Move & power", "Force", "Fields", "Advanced"]) {
    const tab = dock.getByRole("tab", { name, exact: true }); await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    expect(await tab.evaluate(el => getComputedStyle(el, "::after").backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
  }
});

test("Split right creates a second view of the same file, with aligned tabs and resizable groups", async ({ page }, info) => {
  await gotoDesignApp(page);
  await splitRight(page);
  const left = page.getByRole("region", { name: "Left editor group", exact: true });
  const right = page.getByRole("region", { name: "Right editor group", exact: true });
  await expect(left.getByRole("navigation").getByRole("tab")).toHaveText(await right.getByRole("navigation").getByRole("tab").innerText());
  const leftBox = (await left.boundingBox())!, rightBox = (await right.boundingBox())!;
  expect(rightBox.x).toBeGreaterThan(leftBox.x + leftBox.width);
  expect(rightBox.y).toBe(leftBox.y);
  const handle = page.getByRole("separator", { name: "Resize editor groups", exact: true });
  await handle.press("ArrowLeft");
  await expect.poll(async () => (await left.boundingBox())!.width).toBeLessThan(leftBox.width);
  const grip = (await handle.boundingBox())!;
  await page.mouse.move(grip.x + 2, grip.y + grip.height / 2); await page.mouse.down();
  await page.mouse.move(grip.x - 40, grip.y + grip.height / 2, { steps: 5 }); await page.mouse.up();
  await expect.poll(async () => (await left.boundingBox())!.width).toBeLessThan(leftBox.width - 40);
  await page.screenshot({ path: info.outputPath("file-editor-split.png") });
  await right.getByRole("button", { name: /^Close Untitled motor/ }).click();
  await expect(right).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "Save changes?", exact: true })).toHaveCount(0);
  await expect(left.getByRole("navigation").getByRole("tab")).toHaveCount(1);
});

test("dragging file tabs previews the destination, moves in both directions and cancels cleanly", async ({ page }, info) => {
  await gotoDesignApp(page); await newMotor(page);
  const left = page.getByRole("region", { name: "Left editor group", exact: true });
  const source = left.getByRole("navigation").getByRole("tab").last();
  const name = await source.innerText();
  const dataTransfer = await page.evaluateHandle(() => new DataTransfer());
  await source.dispatchEvent("dragstart", { dataTransfer });
  const bounds = (await left.boundingBox())!;
  await left.dispatchEvent("dragover", { dataTransfer, clientX: bounds.x + bounds.width * .8 });
  const preview = page.getByTestId("editor-drop-preview");
  await expect(preview).toBeVisible();
  expect((await preview.boundingBox())!.x).toBeGreaterThan(bounds.x + bounds.width * .4);
  expect(await preview.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
  await page.screenshot({ path: info.outputPath("tab-drop-preview.png") });
  await source.dispatchEvent("dragend");
  await expect(preview).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Right editor group", exact: true })).toHaveCount(0);
  await source.dispatchEvent("dragstart", { dataTransfer });
  await left.dispatchEvent("dragover", { dataTransfer, clientX: bounds.width * .8 });
  await left.dispatchEvent("drop", { dataTransfer });
  const right = page.getByRole("region", { name: "Right editor group", exact: true });
  await expect(right.getByRole("navigation").getByRole("tab")).toHaveText(name);
  await expect(left.getByRole("navigation").getByRole("tab")).toHaveCount(1);
  await right.getByRole("navigation").getByRole("tab").dragTo(left.getByRole("navigation"));
  await expect(right).toHaveCount(0);
  await expect(left.getByRole("navigation").getByRole("tab")).toHaveCount(2);
});

test("split views share source edits but keep their simulation selection independent", async ({ page }) => {
  await gotoDesignApp(page); await splitRight(page);
  const left = page.getByRole("region", { name: "Left editor group", exact: true });
  const right = page.getByRole("region", { name: "Right editor group", exact: true });
  await left.getByRole("tab", { name: "Force", exact: true }).click();
  await expect(right.getByRole("tab", { name: "Move & power", exact: true })).toHaveAttribute("aria-selected", "true");
  await left.getByRole("button", { name: "Magnets", exact: true }).click();
  const count = left.getByRole("spinbutton", { name: "Magnet count", exact: true });
  await count.fill("8"); await count.press("Enter");
  await right.getByRole("button", { name: "Magnets", exact: true }).click();
  await expect(right.getByRole("spinbutton", { name: "Magnet count", exact: true })).toHaveValue("8");
  await expect(left.getByRole("tab", { name: "Force", exact: true })).toHaveAttribute("aria-selected", "true");
});

test("driver calculator opens in a separate window and imports only on request", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: "Force", exact: true }).click();
  await expect(page.getByLabel("Simulation run controls")).toContainText("Results for the active geometry");
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Open driver calculator", exact: true }).click();
  const tool = await popupPromise;
  await expect(tool.getByRole("heading", { name: "Driver calculator", exact: true })).toBeVisible();
  const bus = tool.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await expect(bus).toHaveValue("5");
  await bus.fill("24");
  await selectDesignPanel(page, "Drive & force targets");
  const sourceBus = page.getByRole("spinbutton", { name: "Bus voltage (V)", exact: true });
  await expect(sourceBus).toHaveValue("5");
  await sourceBus.fill("12"); await sourceBus.press("Enter");
  await expect(page.getByLabel("Simulation run controls")).toContainText("Results for the active geometry");
  await expect(bus).toHaveValue("24");
  await tool.getByRole("button", { name: "Import active motor", exact: true }).click();
  await expect(bus).toHaveValue("12");
  await expect(page.getByTestId("driver-check-document")).toHaveCount(0);
  await expect(page.getByRole("separator", { name: "Resize editor groups", exact: true })).toHaveCount(0);
  await tool.close();
  await expect(sourceBus).toHaveValue("12");
});

test("native menu commands target the focused editor and close only that view", async ({ page }) => {
  await installMenuTransport(page);
  await gotoDesignApp(page); await splitRight(page);
  const right = page.getByRole("region", { name: "Right editor group", exact: true });
  const left = page.getByRole("region", { name: "Left editor group", exact: true });
  await right.getByRole("navigation").getByRole("tab").click();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-menu", { detail: "force" })));
  await expect(right.getByRole("tab", { name: "Force", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(left.getByRole("tab", { name: "Move & power", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-menu", { detail: "close" })));
  await expect(right).toHaveCount(0);
  await expect(left.getByRole("navigation").getByRole("tab")).toHaveCount(1);
  await expect(page.getByRole("dialog", { name: "Save changes?", exact: true })).toHaveCount(0);
});

test("the native calculator command can open a blank tool without a source file", async ({ page }) => {
  await installMenuTransport(page);
  await page.goto("/");
  const popup = page.waitForEvent("popup");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-menu", { detail: "driver" })));
  const calculator = await popup;
  await expect(calculator.getByRole("heading", { name: "Driver calculator", exact: true })).toBeVisible();
  await expect(calculator.getByRole("spinbutton", { name: "Hot phase resistance (Ω)", exact: true })).toHaveValue("");
  await calculator.close();
});
