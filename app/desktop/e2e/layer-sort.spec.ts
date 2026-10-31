import { test, expect } from "@playwright/test";
import { gotoDesignApp, openCoilPreview } from "./helpers";
import { installViewMenu } from "./view-menu-helpers";

test.beforeEach(async ({ page }) => { await installViewMenu(page); });

test("Layers replaces Display and sorting preserves filters and the camera in every view", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const rail = workspace.getByRole("toolbar", { name: "Preview side tools", exact: true });
  await expect(rail.getByRole("button", { name: "Display", exact: true })).toHaveCount(0);
  await expect(rail.getByRole("button")).toHaveCount(1);
  await rail.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = workspace.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await expect(panel.getByText("Phases and coils", { exact: true })).toHaveCount(0);
  await expect(panel.getByRole("radiogroup", { name: "Sort by", exact: true })).toBeVisible();
  await expect(panel.getByRole("radio", { name: "Phases", exact: true })).toBeChecked();
  for (const [label, id] of [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]]) {
    await workspace.getByRole("button", { name: label, exact: true }).click();
    const viewer = workspace.getByTestId(`coil-${id}`);
    await expect(viewer).toHaveAttribute("data-camera", /position/);
    await panel.getByRole("checkbox", { name: "Show phase A", exact: true }).uncheck();
    await panel.getByRole("checkbox", { name: "Show A, layer 1", exact: true }).uncheck();
    const count = (await viewer.getAttribute("data-segments"))!, camera = (await viewer.getAttribute("data-camera"))!;
    await panel.getByRole("radio", { name: "Layers", exact: true }).check();
    await expect(panel.getByRole("checkbox", { name: /^Show layer / })).toHaveCount(4);
    await expect(panel.getByRole("checkbox", { name: /^Show phase / })).toHaveCount(0);
    await expect(panel.getByRole("checkbox", { name: /^Show A, layer / })).toHaveCount(4);
    await expect(panel.getByRole("group", { name: "Phase A", exact: true })).toHaveCount(0);
    for (const layer of [1, 2, 3, 4]) {
      const group = panel.getByRole("group", { name: `Layer ${layer}`, exact: true });
      for (const phase of ["A", "B", "C"]) {
        await expect(group.getByRole("button", { name: `Move selection to ${phase}, layer ${layer}`, exact: true })).toHaveText(`Phase ${phase}`);
      }
    }
    await expect(panel.getByRole("checkbox", { name: "Show A, layer 1", exact: true })).not.toBeChecked();
    await expect(viewer).toHaveAttribute("data-segments", count);
    await expect(viewer).toHaveAttribute("data-camera", camera);
    await panel.getByRole("checkbox", { name: "Show layer 0", exact: true }).uncheck();
    // A nested phase toggle changes only that phase/layer pair, not its parents.
    await panel.getByRole("checkbox", { name: "Show B, layer 2", exact: true }).uncheck();
    await expect(panel.getByRole("checkbox", { name: "Show B, layer 1", exact: true })).toBeChecked();
    const filtered = (await viewer.getAttribute("data-segments"))!;
    await panel.getByRole("radio", { name: "Phases", exact: true }).check();
    await expect(panel.getByRole("checkbox", { name: "Show phase A", exact: true })).not.toBeChecked();
    await expect(panel.getByRole("checkbox", { name: "Show A, layer 1", exact: true })).not.toBeChecked();
    await expect(panel.getByRole("checkbox", { name: "Show phase B", exact: true })).toBeChecked();
    await expect(panel.getByRole("checkbox", { name: "Show B, layer 2", exact: true })).not.toBeChecked();
    await expect(viewer).toHaveAttribute("data-segments", filtered);
    await panel.getByRole("checkbox", { name: "Show phase A", exact: true }).check();
    await panel.getByRole("checkbox", { name: "Show A, layer 1", exact: true }).check();
    await panel.getByRole("checkbox", { name: "Show B, layer 2", exact: true }).check();
    await panel.getByRole("radio", { name: "Layers", exact: true }).check();
    await expect(panel.getByRole("checkbox", { name: "Show layer 0", exact: true })).not.toBeChecked();
    await panel.getByRole("checkbox", { name: "Show layer 0", exact: true }).check();
    await panel.getByRole("radio", { name: "Phases", exact: true }).check();
  }
  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    for (const sort of ["Phases", "Layers"]) {
      await panel.getByRole("radio", { name: sort, exact: true }).check();
      await panel.screenshot({ path: info.outputPath(`sort-${sort.toLowerCase()}-${theme}.png`) });
    }
  }
});

test("sort choice survives closing, workflow changes and keyboard changes on mobile", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await gotoDesignApp(page); await openCoilPreview(page);
  const trigger = page.getByRole("button", { name: "Layers", exact: true });
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await trigger.click();
  await panel.getByRole("radio", { name: "Phases", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(panel.getByRole("radio", { name: "Layers", exact: true })).toBeChecked();
  await panel.getByRole("checkbox", { name: "Show layer 1", exact: true }).uncheck();
  await panel.getByRole("button", { name: "Close layers panel", exact: true }).click();
  await expect(trigger).toBeFocused(); await trigger.click();
  await expect(panel.getByRole("radio", { name: "Layers", exact: true })).toBeChecked();
  await expect(panel.getByRole("checkbox", { name: "Show layer 1", exact: true })).not.toBeChecked();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(panel.getByRole("radio", { name: "Layers", exact: true })).toBeChecked();
  const box = (await panel.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: info.outputPath("layers-sort-mobile.png") });
});
