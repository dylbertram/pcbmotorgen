import { test, expect } from "@playwright/test";
import { ASIDE, eventually, gotoDesignApp } from "./helpers";

/**
 * Guards the frontend plumbing of the "traces follow the magnet pattern"
 * invariant: changing magnet geometry must push fresh coil geometry into the
 * preview. (The real backend behaviour is covered by Rust unit tests in
 * `crates/pcbmotorgen-routing`; here the deterministic mock generator also
 * depends on magnet count, so the painted canvas must change.)
 *
 * The canvas viewer exposes introspection attributes on the `<canvas>`:
 * `data-revision` (monotonic draw counter) and `data-segments` (number of
 * trace segments painted in the last frame), plus the routing-dimension
 * overlay counters used by the visibility test below — these replace the
 * retired SVG viewer's DOM `<line>` counting.
 */
test.describe("magnet pattern -> trace regeneration", () => {
  test("changing magnet count regenerates the painted coil traces", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    const canvas = page.locator(
      `${ASIDE} [aria-label='Coil preview'] canvas[data-segments]`,
    );
    await expect(canvas).toBeVisible();

    const segments = async () =>
      Number(await canvas.getAttribute("data-segments"));

    // Wait until coil geometry has been painted — the legend always draws,
    // but no traced segments exist before the first coil payload arrives.
    await eventually(async () => {
      expect(await segments()).toBeGreaterThan(0);
    });

    const before = await segments();
    // Default config: 12 poles -> 24 active conductors per phase
    // (minus end-turns) on every layer.
    expect(before).toBeGreaterThan(100);

    // 6 poles -> 12 active conductors per phase.
    const magnetInput = page.locator("input#magnet-count");
    await magnetInput.fill("6");

    await eventually(async () => {
      expect(await segments()).not.toBe(before);
    });
    // The regenerated layout shrinks: fewer active conductors.
    expect(await segments()).toBeLessThan(before);
  }, { tag: ["@logic", "@desktop"] });
});

test.describe("routing dimensions -> preview overlays", () => {
  test("pole pitch and band-width overlays can be toggled independently", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    const preview = page.locator(`${ASIDE} [aria-label='Coil preview']`);
    const inlineCanvas = preview.locator("canvas[data-pole-pitch]");
    await expect(inlineCanvas).toBeVisible();

    await eventually(async () => {
      expect(await inlineCanvas.getAttribute("data-pole-pitch")).toBe("1");
      expect(Number(await inlineCanvas.getAttribute("data-band-widths"))).toBeGreaterThan(0);
    });

    await page
      .locator(`${ASIDE} button[aria-label='Expand coil preview']`)
      .click();
    const dialog = page.getByRole("dialog", { name: "Coil Preview — expanded" });
    const modalCanvas = dialog.locator("canvas[data-pole-pitch]");
    const polePitch = dialog.getByRole("checkbox", {
      name: "Show pole-pitch dimension ruler",
    });
    const bandWidths = dialog.getByRole("checkbox", {
      name: "Show band-width diagnostics",
    });

    await expect(modalCanvas).toBeVisible();
    await expect(polePitch).toBeChecked();
    await expect(bandWidths).toBeChecked();

    await polePitch.uncheck();
    await eventually(async () => {
      expect(await modalCanvas.getAttribute("data-pole-pitch")).toBe("0");
      expect(Number(await modalCanvas.getAttribute("data-band-widths"))).toBeGreaterThan(0);
    });

    await bandWidths.uncheck();
    await eventually(async () => {
      expect(await modalCanvas.getAttribute("data-pole-pitch")).toBe("0");
      expect(await modalCanvas.getAttribute("data-band-widths")).toBe("0");
    });
  }, { tag: ["@logic", "@desktop"] });

  test("pole-region zones can be filtered by phase and hidden", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    const preview = page.locator(`${ASIDE} [aria-label='Coil preview']`);
    const inlineCanvas = preview.locator("canvas[data-pole-regions]");
    await expect(inlineCanvas).toBeVisible();
    await eventually(async () => {
      expect(Number(await inlineCanvas.getAttribute("data-pole-regions"))).toBeGreaterThan(0);
    });

    await page
      .locator(`${ASIDE} button[aria-label='Expand coil preview']`)
      .click();
    const dialog = page.getByRole("dialog", { name: "Coil Preview — expanded" });
    const modalCanvas = dialog.locator("canvas[data-pole-regions]");
    const regionsToggle = dialog.getByRole("checkbox", { name: "Show pole regions" });
    const phaseSelect = dialog.getByRole("combobox", { name: "Pole regions phase" });
    const phaseB = dialog.getByRole("checkbox", { name: "Show phase B" });

    await expect(modalCanvas).toBeVisible();
    await expect(regionsToggle).toBeChecked();
    await expect(phaseSelect).toBeEnabled();
    await expect(phaseB).toBeChecked();

    const allRegions = Number(await modalCanvas.getAttribute("data-pole-regions"));
    await phaseSelect.selectOption("B");
    await eventually(async () => {
      const selectedRegions = Number(await modalCanvas.getAttribute("data-pole-regions"));
      expect(selectedRegions).toBeGreaterThan(0);
      expect(selectedRegions).toBeLessThan(allRegions);
      // Selecting a pole-region phase must not change trace phase visibility.
      await expect(phaseB).toBeChecked();
    });

    await regionsToggle.uncheck();
    await eventually(async () => {
      expect(await modalCanvas.getAttribute("data-pole-regions")).toBe("0");
      await expect(phaseSelect).toBeDisabled();
    });
  }, { tag: ["@logic", "@desktop"] });
});
