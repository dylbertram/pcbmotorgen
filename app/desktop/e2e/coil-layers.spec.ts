import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

// Migrated from the retired modal to the persistent workspace. Modal margins,
// header styling and the embedded waveform popover were intentionally removed
// by ui-cleanup. Their replacements are workspace containment and dock checks.
async function workspace(page: Page) {
  await gotoDesignApp(page);
  const view = page.getByRole("region", { name: "Coil design workspace", exact: true });
  const selected = view.getByRole("toolbar", { name: "Design side tools", exact: true }).locator('button[aria-expanded="true"]');
  if (await selected.count()) await selected.click();
  return view;
}

test("zoom controls clear every open side panel", async ({ page }, testInfo) => {
  const view = await workspace(page);
  const zoom = view.getByRole("group", { name: "Zoom controls" });
  for (const size of [{ width: 1280, height: 800 }, { width: 640, height: 480 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    const resting = (await zoom.boundingBox())!;
    for (const [trigger, name] of [["Layers", "Coil preview layers"], ["Display", "Coil preview display"], ["Set coil terminals", "Coil terminals"], ["Driver settings", "Preview driver settings"]]) {
      await view.getByRole("button", { name: trigger, exact: true }).click();
      const panel = view.getByRole("dialog", { name, exact: true });
      await expect(panel).toBeVisible();
      if (size.width < 640) {
        await expect(zoom).toBeHidden();
      } else {
        await expect(zoom).toBeVisible();
        await expect.poll(async () => {
          const z = (await zoom.boundingBox())!, p = (await panel.boundingBox())!;
          return z.x + z.width <= p.x || p.x + p.width <= z.x;
        }).toBe(true);
        await view.getByRole("button", { name: "Zoom in", exact: true }).click();
      }
      const last = panel.locator("button, input").last();
      await last.scrollIntoViewIfNeeded();
      await last.click({ trial: true });
      if (trigger === "Layers") await page.screenshot({ path: testInfo.outputPath(`panel-clearance-${size.width}.png`) });
      await view.getByRole("button", { name: trigger, exact: true }).click();
      await expect(panel).toHaveCount(0);
      await expect(zoom).toBeVisible();
      const restored = (await zoom.boundingBox())!;
      expect(restored.x + restored.width).toBeCloseTo(resting.x + resting.width, 0);
    }
  }
});

test("persistent workspace edits and middle-drag panning survive workflow changes", async ({ page }) => {
  const view = await workspace(page);
  const frame = view.getByRole("img", { name: "Coil preview", exact: true });
  const canvas = frame.locator("canvas");
  await expect(view.getByRole("button", { name: "Edit segments", exact: true })).toBeVisible();
  const revision = await canvas.getAttribute("data-revision");
  const box = (await frame.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down({ button: "middle" });
  await expect(frame).toHaveCSS("cursor", "grabbing");
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 20, { steps: 5 });
  await page.mouse.up({ button: "middle" });
  await expect(canvas).not.toHaveAttribute("data-revision", revision!);
  await expect(frame).toHaveCSS("cursor", "grab");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(frame).toBeVisible();
  await expect(page.getByRole("button", { name: "Open coil preview", exact: true })).toHaveCount(0);
});

test("copper width is zoom-independent in world units; centerlines remain thin", async ({ page }) => {
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.stroke;
    CanvasRenderingContext2D.prototype.stroke = function (...args: [Path2D?]) {
      if (this.strokeStyle === "#10b981") {
        this.canvas.dataset.testWorldWidth = String(this.lineWidth);
        this.canvas.dataset.testPixelWidth = String(this.lineWidth * Math.abs(this.getTransform().a));
      }
      if (args[0]) original.call(this, args[0]); else original.call(this);
    };
  });
  const view = await workspace(page), canvas = view.getByRole("img", { name: "Coil preview", exact: true }).locator("canvas");
  await expect(canvas).toHaveAttribute("data-test-world-width", /\d/);
  const width = (await canvas.getAttribute("data-test-world-width"))!;
  const pixels = Number(await canvas.getAttribute("data-test-pixel-width"));
  await view.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(canvas).toHaveAttribute("data-test-world-width", width);
  await expect.poll(async () => Number(await canvas.getAttribute("data-test-pixel-width"))).toBeGreaterThan(pixels);
  await view.getByRole("button", { name: "Display", exact: true }).click();
  const panel = view.getByRole("dialog", { name: "Coil preview display", exact: true });
  await panel.getByRole("radio", { name: "Centerlines" }).check();
  await panel.getByRole("button", { name: "Close display panel" }).click();
  await expect(canvas).toHaveAttribute("data-trace-mode", "centerlines");
  const thin = Number(await canvas.getAttribute("data-test-pixel-width"));
  await view.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect.poll(async () => Number(await canvas.getAttribute("data-test-pixel-width"))).toBeCloseTo(thin);
});

test("side rail panels do not resize the drawing and keep display choices", async ({ page }) => {
  const view = await workspace(page), canvas = view.getByRole("img", { name: "Coil preview", exact: true }).locator("canvas");
  const bounds = await canvas.boundingBox();
  const rail = view.getByRole("toolbar", { name: "Preview side tools" });
  await expect(rail).toHaveAttribute("aria-orientation", "vertical");
  await view.getByRole("button", { name: "Layers", exact: true }).click();
  const layers = view.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await expect(layers).toBeVisible();
  expect(await canvas.boundingBox()).toEqual(bounds);
  await view.getByRole("button", { name: "Display", exact: true }).click();
  await expect(layers).toHaveCount(0);
  const display = view.getByRole("dialog", { name: "Coil preview display", exact: true });
  await display.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
  await expect(canvas).toHaveAttribute("data-vias", "0");
  await display.getByRole("radio", { name: "Centerlines" }).check();
  await display.getByRole("button", { name: "Close display panel" }).click();
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await view.getByRole("button", { name: "Display", exact: true }).click();
  await expect(display.getByRole("checkbox", { name: "Show vias", exact: true })).not.toBeChecked();
  await expect(display.getByRole("radio", { name: "Centerlines" })).toBeChecked();
});

test("outside drawing clicks keep panels open; toggles close them", async ({ page }) => {
  const view = await workspace(page);
  for (const [trigger, name] of [["Layers", "Coil preview layers"], ["Display", "Coil preview display"]]) {
    await view.getByRole("button", { name: trigger, exact: true }).click();
    const panel = view.getByRole("dialog", { name, exact: true });
    await expect(panel).toBeVisible();
    const box = (await view.getByRole("img", { name: "Coil preview", exact: true }).boundingBox())!;
    await page.mouse.click(box.x + box.width * .25, box.y + box.height * .5);
    await expect(panel).toBeVisible();
    await view.getByRole("button", { name: trigger, exact: true }).click();
    await expect(panel).toHaveCount(0);
  }
});

test("Threlte renders copper and supports orbit, zoom, pan and visibility", async ({ page }, testInfo) => {
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => {
    const draw = WebGL2RenderingContext.prototype.drawElements;
    WebGL2RenderingContext.prototype.drawElements = function (...args) {
      const canvas = this.canvas as HTMLCanvasElement;
      canvas.dataset.draws = String(Number(canvas.dataset.draws ?? 0) + 1);
      return draw.apply(this, args);
    };
  });
  const view = await workspace(page);
  await view.getByRole("button", { name: "Display", exact: true }).click();
  const modes = view.getByRole("dialog", { name: "Coil preview display", exact: true });
  await view.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await modes.getByRole("button", { name: "Close display panel" }).click();
  const iso = view.getByTestId("coil-iso"), canvas = iso.locator("canvas");
  await expect.poll(async () => Number(await canvas.getAttribute("data-draws"))).toBeGreaterThan(0);
  await expect(iso).toHaveAttribute("data-vias", /[1-9]/);
  const segments = Number(await iso.getAttribute("data-segments"));
  await view.getByRole("button", { name: "Display", exact: true }).click();
  const display = view.getByRole("dialog", { name: "Coil preview display", exact: true });
  await display.getByRole("checkbox", { name: "Show layer 0", exact: true }).uncheck();
  await expect.poll(async () => Number(await iso.getAttribute("data-segments"))).toBeLessThan(segments);
  await display.getByRole("checkbox", { name: "Show layer 0", exact: true }).check();
  await display.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
  await expect(iso).toHaveAttribute("data-vias", "0");
  await display.getByRole("checkbox", { name: "Show vias", exact: true }).check();
  await display.getByRole("radio", { name: "Centerlines" }).check();
  await expect(iso).toHaveAttribute("data-trace-mode", "centerlines");
  await display.getByRole("button", { name: "Close display panel" }).click();
  const before = await canvas.screenshot(), box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * .4, box.y + box.height * .45);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .55, box.y + box.height * .6, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false);
  const orbited = await canvas.screenshot();
  await iso.getByRole("button", { name: "Zoom in 3D", exact: true }).click();
  await expect.poll(async () => (await canvas.screenshot()).equals(orbited)).toBe(false);
  const zoomed = await canvas.screenshot();
  await page.mouse.move(box.x + box.width * .4, box.y + box.height * .45); await page.mouse.wheel(0, -160);
  await expect.poll(async () => (await canvas.screenshot()).equals(zoomed)).toBe(false);
  const scrolled = await canvas.screenshot();
  await page.mouse.down({ button: "right" });
  await page.mouse.move(box.x + box.width * .45, box.y + box.height * .5, { steps: 5 });
  await page.mouse.up({ button: "right" });
  await expect.poll(async () => (await canvas.screenshot()).equals(scrolled)).toBe(false);
  await iso.getByRole("button", { name: "Reset 3D view", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("coil-iso.png") });
  await view.getByRole("button", { name: "Display", exact: true }).click();
  await view.getByRole("button", { name: "Top-down", exact: true }).click();
  await expect(iso).toHaveCount(0);
  await expect(view.getByRole("img", { name: "Coil preview", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("overlay visibility and phase selection preserve camera", async ({ page }) => {
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.scale;
    CanvasRenderingContext2D.prototype.scale = function (x, y) {
      original.call(this, x, y);
      const t = this.getTransform(); this.canvas.dataset.testCamera = JSON.stringify([t.a, t.d, t.e, t.f]);
    };
  });
  const view = await workspace(page), canvas = view.getByRole("img", { name: "Coil preview", exact: true }).locator("canvas");
  await view.getByRole("button", { name: "Zoom in", exact: true }).click();
  await view.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = view.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await panel.getByRole("checkbox", { name: "Show pole regions", exact: true }).check();
  await expect(canvas).toHaveAttribute("data-pole-regions", /[1-9]/);
  const camera = (await canvas.getAttribute("data-test-camera"))!;
  await panel.getByRole("combobox", { name: "Pole regions phase" }).selectOption({ index: 1 });
  await expect(canvas).toHaveAttribute("data-test-camera", camera);
  for (const name of ["Show pole-pitch dimension ruler", "Show band-width diagnostics", "Show pole regions"]) {
    const revision = await canvas.getAttribute("data-revision");
    await panel.getByRole("checkbox", { name, exact: true }).click();
    await expect(canvas).not.toHaveAttribute("data-revision", revision!);
    await expect(canvas).toHaveAttribute("data-test-camera", camera);
  }
});

test("workspace contains drawing controls at desktop and phone widths", async ({ page }) => {
  const view = await workspace(page);
  for (const size of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    const drawing = (await view.getByRole("img", { name: "Coil preview", exact: true }).boundingBox())!;
    for (const control of [view.getByRole("toolbar", { name: "Coil preview tools" }), view.getByRole("group", { name: "Zoom controls" }), view.getByRole("slider", { name: "Mover position slider (mm)" })]) {
      const box = (await control.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(drawing.x);
      expect(box.y).toBeGreaterThanOrEqual(drawing.y);
      expect(box.x + box.width).toBeLessThanOrEqual(drawing.x + drawing.width + 1);
      expect(box.y + box.height).toBeLessThanOrEqual(drawing.y + drawing.height + 1);
    }
  }
});

test("position controls stay aligned and waveform lives in the simulation dock", async ({ page }) => {
  const view = await workspace(page);
  const position = view.getByRole("spinbutton", { name: "Mover position (mm)", exact: true });
  const slider = view.getByRole("slider", { name: "Mover position slider (mm)", exact: true });
  await expect.poll(async () => {
    const p = (await position.boundingBox())!, s = (await slider.boundingBox())!;
    return Math.abs(p.y + p.height / 2 - s.y - s.height / 2);
  }).toBeLessThan(2);
  await expect(view.getByRole("dialog", { name: "Phase waveform", exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await expect(page.getByRole("region", { name: "Simulation results", exact: true })).toBeVisible();
  await expect(position).toBeVisible();
});

test("workflow changes preserve mover position and keep the preview mounted", async ({ page }) => {
  const view = await workspace(page);
  const position = view.getByRole("spinbutton", { name: "Mover position (mm)", exact: true });
  const value = await position.inputValue();
  const canvas = view.getByRole("img", { name: "Coil preview", exact: true }).locator("canvas");
  await canvas.evaluate(el => el.setAttribute("data-mount-witness", "retained"));
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  await page.getByRole("tab", { name: /^Design/i }).click();
  await expect(position).toHaveValue(value);
  await expect(canvas).toHaveAttribute("data-mount-witness", "retained");
});
