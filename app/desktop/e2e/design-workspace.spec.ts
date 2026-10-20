import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

const sections = [
  { name: "Constraints", heading: "design-constraints-heading" },
  { name: "Stackup", heading: "backplane-heading" },
  { name: "Routing", heading: "topology-board-heading" },
  { name: "Drive & force targets", heading: "drive-targets-heading" },
  { name: "Magnets", heading: "magnets-heading" },
];

test("each design section has its own left-side button and panel", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const left = workspace.getByRole("toolbar", { name: "Design side tools", exact: true });
  const right = workspace.getByRole("toolbar", { name: "Preview side tools", exact: true });
  await expect(left.getByRole("button")).toHaveCount(7);
  await expect(page.getByRole("button", { name: "Design settings", exact: true })).toHaveCount(0);
  await expect(workspace.getByRole("heading", { name: "Coil Preview", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Expand coil preview", exact: true })).toHaveCount(0);
  await expect(page.locator("footer")).toHaveCount(0);
  await expect(page.getByLabel("Coil geometry summary")).toHaveText("3 phases · 4 layers · 12 coil groups");
  const drawing = workspace.getByRole("img", { name: "Coil preview", exact: true });
  const drawingBounds = await drawing.boundingBox();

  for (const section of sections) {
    const trigger = left.getByRole("button", { name: section.name, exact: true });
    if (await trigger.getAttribute("aria-expanded") !== "true") await trigger.click();
    const panel = workspace.getByRole("dialog", { name: section.name, exact: true });
    await expect(panel).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await expect(right.getByRole("button", { name: section.name, exact: true })).toHaveCount(0);
    const content = panel.locator(`#${section.heading}`);
    await expect(content).toBeVisible();
    await expect(content).toHaveCSS("border-top-width", "0px");
    await expect(content).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(content).toHaveCSS("padding", "0px");
    await expect(content.getByRole("heading", { name: /^(Design constraints|Topology & board|Stackup|Magnets)$/ })).toHaveCount(0);
    await expect(panel.getByRole("heading", { name: section.name, exact: true })).toHaveCount(1);
    for (const other of sections.filter((other) => other !== section)) {
      await expect(workspace.getByRole("dialog", { name: other.name, exact: true })).toHaveCount(0);
      await expect(panel.locator(`#${other.heading}`)).toHaveCount(0);
    }
    const railBounds = (await left.boundingBox())!;
    await expect.poll(async () => (await panel.boundingBox())!.x).toBe(railBounds.x + railBounds.width);
    expect(await drawing.boundingBox()).toEqual(drawingBounds);
    await page.screenshot({ path: testInfo.outputPath(`${section.name.toLowerCase()}.png`) });
  }
  const magnets = workspace.getByRole("dialog", { name: "Magnets", exact: true });
  await magnets.getByRole("button", { name: "Close magnets panel", exact: true }).click();
  await expect(magnets).toHaveCount(0);
  await expect(left.getByRole("button", { name: "Magnets", exact: true })).toBeFocused();
});

test("coil ends and driver controls dock on the left in both workflows", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  for (const workflow of ["Design", "Simulate"]) {
    await page.getByRole("tab", { name: new RegExp(`^${workflow}`, "i") }).click();
    const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
    const left = workspace.getByRole("toolbar", { name: "Design side tools", exact: true });
    const right = workspace.getByRole("toolbar", { name: "Preview side tools", exact: true });
    await expect(right.getByRole("button")).toHaveCount(2);
    for (const item of [
      { button: "Set coil terminals", dialog: "Coil terminals", close: "Close terminals panel" },
      { button: "Driver settings", dialog: "Preview driver settings", close: "Close driver panel" },
    ]) {
      await expect(right.getByRole("button", { name: item.button, exact: true })).toHaveCount(0);
      const trigger = left.getByRole("button", { name: item.button, exact: true });
      await trigger.click();
      const panel = workspace.getByRole("dialog", { name: item.dialog, exact: true });
      await expect(panel).toBeVisible();
      const railBounds = (await left.boundingBox())!;
      await expect.poll(async () => (await panel.boundingBox())!.x).toBe(railBounds.x + railBounds.width);
      if (item.button === "Driver settings") {
        await expect(panel.getByRole("combobox", { name: "Driver to evaluate" })).toBeVisible();
      } else {
        await expect(panel.getByRole("region", { name: "Set coil terminals", exact: true })).toBeVisible();
      }
      await page.screenshot({ path: testInfo.outputPath(`${workflow.toLowerCase()}-${item.button === "Driver settings" ? "driver" : "ends"}.png`) });
      await panel.getByRole("button", { name: item.close, exact: true }).click();
      await expect(trigger).toBeFocused();
      await trigger.click();
      await page.keyboard.press("Escape");
      await expect(panel).toHaveCount(0);
      await expect(trigger).toBeFocused();
    }
  }
});

test("edits survive panel changes and workflow changes", async ({ page }) => {
  await gotoDesignApp(page);
  const left = page.getByRole("toolbar", { name: "Design side tools", exact: true });
  const travel = page.getByRole("spinbutton", { name: "Desired travel (center-to-center)", exact: true });
  await travel.fill("100");
  await travel.press("Enter");
  await left.getByRole("button", { name: "Magnets", exact: true }).click();
  const count = page.getByRole("spinbutton", { name: "Magnet count", exact: true });
  await count.fill("14");
  await count.press("Enter");
  await left.getByRole("button", { name: "Routing", exact: true }).click();
  await page.getByRole("combobox", { name: "Winding connection", exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Driver settings", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Routing", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Preview driver simulation results" })).toContainText("Current ripple");
  await left.getByRole("button", { name: "Constraints", exact: true }).click();
  await expect(travel).toHaveValue("100");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.getByRole("dialog", { name: "Constraints", exact: true })).toBeVisible();
  await left.getByRole("button", { name: "Magnets", exact: true }).click();
  await expect(count).toHaveValue("14");
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(page.getByRole("dialog", { name: "Magnets", exact: true })).toBeVisible();
  await expect(count).toHaveValue("14");
});

test("Escape closes only the selected panel and returns focus to its button", async ({ page }) => {
  await gotoDesignApp(page);
  const left = page.getByRole("toolbar", { name: "Design side tools", exact: true });
  for (const section of sections) {
    const trigger = left.getByRole("button", { name: section.name, exact: true });
    if (await trigger.getAttribute("aria-expanded") !== "true") await trigger.click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: section.name, exact: true })).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
  }
});

test("returning from Simulate repaints canvas pixels and preserves the selected panel", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Stackup", exact: true }).click();
  const canvas = page.locator("#panel-design canvas");
  const paintedPixels = () => canvas.evaluate((node: HTMLCanvasElement) => {
    const pixels = node.getContext("2d")!.getImageData(0, 0, node.width, node.height).data;
    let painted = 0;
    for (let i = 3; i < pixels.length; i += 4) if (pixels[i]) painted++;
    return painted;
  });
  await expect.poll(paintedPixels).toBeGreaterThan(100);
  for (let cycle = 0; cycle < 3; cycle++) {
    const revision = Number(await canvas.getAttribute("data-revision"));
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    await page.getByRole("tab", { name: /^Design/i }).click();
    await expect(page.getByRole("dialog", { name: "Stackup", exact: true })).toBeVisible();
    await expect.poll(() => canvas.getAttribute("data-revision").then(Number)).toBeGreaterThan(revision);
    await expect.poll(paintedPixels).toBeGreaterThan(100);
  }
});

test("all seven left panels fit mobile without moving or overflowing the canvas", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page);
  const left = page.getByRole("toolbar", { name: "Design side tools", exact: true });
  for (const section of [
    ...sections.map(({ name }) => ({ button: name, dialog: name })),
    { button: "Set coil terminals", dialog: "Coil terminals" },
    { button: "Driver settings", dialog: "Preview driver settings" },
  ]) {
    const trigger = left.getByRole("button", { name: section.button, exact: true });
    if (await trigger.getAttribute("aria-expanded") !== "true") await trigger.click();
    const panel = page.getByRole("dialog", { name: section.dialog, exact: true });
    await expect(panel).toBeVisible();
    const viewport = panel.locator("[data-scroll-area-viewport]");
    if (await viewport.count()) await viewport.evaluate((el) => { el.scrollTop = el.scrollHeight; });
    const bounds = (await panel.boundingBox())!;
    await expect.poll(async () => (await panel.boundingBox())!.x).toBe(44);
    expect(bounds.width).toBeLessThanOrEqual(258);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(844);
    await page.screenshot({ path: testInfo.outputPath(`${section.dialog.toLowerCase().replaceAll(" ", "-")}-mobile.png`) });
  }
});
