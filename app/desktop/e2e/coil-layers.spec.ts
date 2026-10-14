import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("inline motor preview is read-only and pans with the primary drag", async ({ page }) => {
  await gotoDesignApp(page);
  const inline = page.getByRole("img", { name: "Coil preview", exact: true });
  await expect(inline).toBeVisible();
  await expect(page.getByRole("toolbar", { name: "Coil preview tools" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Zoom controls" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Simplify lines", exact: true })).toHaveCount(0);
  const canvas = inline.locator("canvas");
  const revision = Number(await canvas.getAttribute("data-revision"));
  await inline.scrollIntoViewIfNeeded();
  await expect(inline).toHaveCSS("cursor", "grab");
  const box = (await inline.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(inline).toHaveCSS("cursor", "grabbing");
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 20, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => Number(await canvas.getAttribute("data-revision"))).toBeGreaterThan(revision);
  await expect(page.getByRole("dialog", { name: "Coil Preview", exact: true })).toHaveCount(0);
  await expect(inline).toHaveCSS("cursor", "grab");
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await expect(page.getByRole("dialog", { name: "Coil Preview", exact: true })).toBeVisible();
});

test("copper width is zoom-independent in world units; centerlines remain thin", async ({ page }) => {
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.stroke;
    CanvasRenderingContext2D.prototype.stroke = function (...args: [Path2D?]) {
      if (this.strokeStyle === "#10b981") {
        this.canvas.dataset.testWorldWidth = String(this.lineWidth);
        this.canvas.dataset.testPixelWidth = String(this.lineWidth * Math.abs(this.getTransform().a));
      }
      if (args[0]) original.call(this, args[0]);
      else original.call(this);
    };
  });
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  const canvas = dialog.locator("canvas");
  await expect(canvas).toHaveAttribute("data-trace-mode", "traces");
  await expect(canvas).toHaveAttribute("data-test-world-width", /\d/);
  const width = await canvas.getAttribute("data-test-world-width");
  const pixels = Number(await canvas.getAttribute("data-test-pixel-width"));
  await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(canvas).toHaveAttribute("data-test-world-width", width!);
  await expect.poll(async () => Number(await canvas.getAttribute("data-test-pixel-width"))).toBeGreaterThan(pixels);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await panel.getByRole("radio", { name: "Centerlines" }).check();
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await expect(canvas).toHaveAttribute("data-trace-mode", "centerlines");
  const centerlinePixels = Number(await canvas.getAttribute("data-test-pixel-width"));
  await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect.poll(async () => Number(await canvas.getAttribute("data-test-pixel-width"))).toBeCloseTo(centerlinePixels);
});

test("all toggles live in the Layers popover and survive reopening without resizing the viewer", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  const canvasBox = await dialog.locator("canvas").boundingBox();
  const rail = dialog.getByRole("toolbar", { name: "Preview side tools" });
  await expect(rail).toHaveAttribute("aria-orientation", "vertical");
  const railBounds = (await rail.boundingBox())!;
  expect(railBounds.x + railBounds.width).toBeCloseTo(canvasBox!.x + canvasBox!.width, 0);
  expect(railBounds.y).toBeGreaterThan(canvasBox!.y);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await expect(panel).toBeVisible();
  const panelBounds = (await panel.boundingBox())!;
  expect(panelBounds.x + panelBounds.width).toBeLessThanOrEqual(railBounds.x + 4);
  expect(await dialog.locator("canvas").boundingBox()).toEqual(canvasBox);
  expect(await dialog.getByRole("checkbox").count()).toBe(0);
  await panel.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
  await expect(dialog.locator("canvas")).toHaveAttribute("data-vias", "0");
  await panel.getByRole("radio", { name: "Centerlines" }).check();
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  const toolbar = dialog.getByRole("toolbar", { name: "Coil preview tools" });
  expect((await toolbar.boundingBox())!.y).toBeGreaterThan(canvasBox!.y);
  await toolbar.getByRole("button", { name: "Toggle measure tool" }).click();
  await expect(toolbar.getByRole("button", { name: "Toggle measure tool" })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await expect(panel.getByRole("checkbox", { name: "Show vias", exact: true })).not.toBeChecked();
  await expect(panel.getByRole("radio", { name: "Centerlines" })).toBeChecked();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel).toBeVisible();
  expect((await dialog.boundingBox())!.width).toBeLessThan(390);
});

test("overlay visibility and phase selection do not change the camera", async ({ page }) => {
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.scale;
    CanvasRenderingContext2D.prototype.scale = function (x: number, y: number) {
      original.call(this, x, y);
      const transform = this.getTransform();
      this.canvas.dataset.testCamera = JSON.stringify([transform.a, transform.d, transform.e, transform.f]);
    };
  });
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  const canvas = dialog.locator("canvas");
  await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
  const frame = dialog.getByRole("img", { name: "Coil preview — expanded", exact: true });
  const box = (await frame.boundingBox())!;
  await page.mouse.move(box.x + 100, box.y + 100);
  await page.mouse.down({ button: "middle" });
  await page.mouse.move(box.x + 130, box.y + 120);
  await page.mouse.up({ button: "middle" });
  await expect(canvas).toHaveAttribute("data-test-camera", /\[/);
  const camera = (await canvas.getAttribute("data-test-camera"))!;
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  const phase = panel.getByRole("combobox", { name: "Pole regions phase" });
  await phase.selectOption({ index: 1 });
  await expect(canvas).toHaveAttribute("data-test-camera", camera);
  for (const name of ["Show pole-pitch dimension ruler", "Show band-width diagnostics", "Show pole regions"]) {
    const revision = await canvas.getAttribute("data-revision");
    await panel.getByRole("checkbox", { name, exact: true }).uncheck();
    await expect(canvas).not.toHaveAttribute("data-revision", revision!);
    await expect(canvas).toHaveAttribute("data-test-camera", camera);
  }
});

test("full-modal drawing contains docked controls and bottom display menu", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  for (const size of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    const frame = dialog.getByRole("img", { name: "Coil preview — expanded", exact: true });
    // The modal clears the 36px title bar (traffic lights) and keeps a
    // margin all around, so the drawing fills the rest of the viewport.
    const modal = (await dialog.boundingBox())!;
    expect(modal.y).toBeGreaterThanOrEqual(44);
    expect(modal.x).toBeGreaterThanOrEqual(20);
    expect(modal.y + modal.height).toBeLessThanOrEqual(size.height - 20);
    await expect.poll(async () => (await frame.boundingBox())!.height).toBeGreaterThan(size.height - 90);
    const drawing = (await frame.boundingBox())!;
    for (const control of [dialog.getByRole("toolbar", { name: "Coil preview tools" }), dialog.getByRole("group", { name: "Zoom controls" }), dialog.getByRole("group", { name: "Preview status" }), dialog.getByRole("slider", { name: "Mover position slider (mm)" })]) {
      const box = (await control.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(drawing.x);
      expect(box.y).toBeGreaterThanOrEqual(drawing.y);
      expect(box.x + box.width).toBeLessThanOrEqual(drawing.x + drawing.width);
      expect(box.y + box.height).toBeLessThanOrEqual(drawing.y + drawing.height);
    }
    await dialog.getByRole("button", { name: "Display state" }).click();
    await page.getByRole("menuitemcheckbox", { name: "Show phase waveform" }).click();
    await expect(dialog.getByRole("img", { name: /Per-phase holding force versus mover position/ })).toHaveCount(0);
    await expect(dialog.getByRole("slider", { name: "Mover position slider (mm)" })).toBeVisible();
    await dialog.getByRole("button", { name: "Display state" }).click();
    await page.getByRole("menuitemcheckbox", { name: "Show phase waveform" }).click();
    await expect(dialog.getByRole("img", { name: /Per-phase holding force versus mover position/ })).toBeVisible();
  }
});

test("the modal toolbar and zoom controls are bare, the position box is outlined, and the waveform pops above it", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  for (const size of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    const toolbar = dialog.getByRole("toolbar", { name: "Coil preview tools" });
    const zoom = dialog.getByRole("group", { name: "Zoom controls" });
    const position = dialog.getByRole("spinbutton", { name: "Mover position (mm)", exact: true });
    const slider = dialog.getByRole("slider", { name: "Mover position slider (mm)", exact: true });
    const positionBox = position.locator('xpath=ancestor::div[@aria-label="Mover position"]/..');
    for (const bare of [toolbar, toolbar.locator(".."), zoom, zoom.locator("..")]) {
      expect(await bare.evaluate((el) => getComputedStyle(el).borderTopWidth)).toBe("0px");
    }
    // The position box has its outline and backing back.
    expect(await positionBox.evaluate((el) => getComputedStyle(el).borderTopWidth)).not.toBe("0px");
    expect(await positionBox.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
    await expect.poll(async () => {
      const inputBox = (await position.boundingBox())!;
      const sliderBox = (await slider.boundingBox())!;
      return Math.abs(inputBox.y + inputBox.height / 2 - sliderBox.y - sliderBox.height / 2);
    }).toBeLessThan(2);
    // The graph lives in its own fixed popover, never in the position box.
    const popover = dialog.getByRole("dialog", { name: "Phase waveform", exact: true });
    await expect(popover).toBeVisible();
    await expect(popover.getByRole("img", { name: /Per-phase holding force versus mover position/ })).toBeVisible();
    await expect(positionBox.getByRole("img", { name: /Per-phase/ })).toHaveCount(0);
    const box = (await positionBox.boundingBox())!;
    const pop = (await popover.boundingBox())!;
    expect(pop.width).toBeCloseTo(box.width, 0);
    expect(pop.x).toBeCloseTo(box.x, 0);
    expect(pop.y + pop.height).toBeLessThanOrEqual(box.y + 1);
    // The X closes it and clears the Display item.
    await popover.getByRole("button", { name: "Close phase waveform" }).click();
    await expect(popover).toHaveCount(0);
    await dialog.getByRole("button", { name: "Display state" }).click();
    await expect(page.getByRole("menuitemcheckbox", { name: "Show phase waveform" })).toHaveAttribute("aria-checked", "false");
    await page.getByRole("menuitemcheckbox", { name: "Show phase waveform" }).click();
    await expect(popover).toBeVisible();
    await expect(position).toBeVisible();
  }
});

test("phase waveform visibility preserves mover controls and survives reopening", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  const toggle = panel.getByRole("checkbox", { name: "Show phase waveform", exact: true });
  const waveform = dialog.getByRole("img", { name: /Per-phase holding force versus mover position/ });
  const position = dialog.getByRole("spinbutton", { name: "Mover position (mm)", exact: true });
  const slider = dialog.getByRole("slider", { name: "Mover position slider (mm)", exact: true });
  await expect(toggle).toBeChecked();
  await expect(waveform).toBeVisible();
  const value = await position.inputValue();
  await toggle.uncheck();
  await expect(waveform).toHaveCount(0);
  await expect(position).toBeVisible();
  await expect(position).toHaveValue(value);
  await expect(slider).toBeVisible();
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await expect(toggle).not.toBeChecked();
  await expect(waveform).toHaveCount(0);
  await toggle.check();
  await expect(waveform).toBeVisible();
  expect((await toggle.locator("..").getAttribute("title"))!.length).toBeLessThanOrEqual(140);
});
