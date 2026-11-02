import { expect, test, type Page } from "@playwright/test";

async function openSensor(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Sensor coil/ }).click();
}

async function checkFields(page: Page) {
  const settings = page.locator("#sensor-settings-scroll");
  const failures = await settings.locator("label:has(input[type=number])").evaluateAll(labels => labels.flatMap(label => {
    const input = label.querySelector("input")!;
    const text = label.querySelector("span")!;
    const card = label.closest("section")!;
    const a = input.getBoundingClientRect(), b = card.getBoundingClientRect();
    return a.left < b.left || a.right > b.right || input.scrollWidth > input.clientWidth + 2 || text.scrollWidth > text.clientWidth + 1
      ? [input.getAttribute("aria-label")] : [];
  }));
  expect(failures).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize()!.width);
  const last = settings.getByRole("spinbutton", { name: "TX via size (mm)", exact: true });
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeInViewport();
  await last.fill("0.7");
  await last.press("Tab");
  await expect(last).toHaveValue("0.7");
}

test("sensor fields and preview reflow without clipping at full and narrow widths", async ({ page }, info) => {
  await openSensor(page);
  for (const width of [1544, 1100, 800, 390]) {
    await page.setViewportSize({ width, height: 850 });
    await checkFields(page);
    await page.locator("#sensor-settings-scroll [data-scroll-area-viewport]").evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: info.outputPath(`sensor-${width}.png`) });
  }
  await page.setViewportSize({ width: 1100, height: 850 });
  await page.addStyleTag({ content: "html { font-size: 20px; }" });
  await checkFields(page);
});

test("sensor panes reflow to the width of a split editor rather than the window", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openSensor(page);
  await page.getByRole("navigation", { name: "Open files", exact: true }).getByRole("tab").click({ button: "right" });
  await page.getByRole("menuitem", { name: "Split right", exact: true }).click();
  for (const side of ["Left", "Right"]) {
    const group = page.getByRole("region", { name: `${side} editor group`, exact: true });
    const preview = (await group.getByRole("complementary", { name: "Coil preview panel", exact: true }).boundingBox())!;
    const settings = (await group.locator("#sensor-settings-scroll").boundingBox())!;
    expect(settings.y).toBeGreaterThanOrEqual(preview.y + preview.height - 1);
    const last = group.getByRole("spinbutton", { name: "TX via size (mm)", exact: true });
    await last.scrollIntoViewIfNeeded();
    await expect(last).toBeInViewport();
    expect(await group.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  }
});
