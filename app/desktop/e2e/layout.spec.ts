import { test, expect } from "@playwright/test";
import {
  DESIGN_SCROLL,
  designPanel,
  leftColumnFirstCard,
  ASIDE,
  box,
  gotoDesignApp,
} from "./helpers";

test.describe("Design tab layout geometry", () => {
  test("design scroll viewports meet the header and footer dividers", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await gotoDesignApp(page);
    const nav = (await page.getByRole("navigation", { name: "Design workflows" }).boundingBox())!;
    const footer = (await page.locator("footer").boundingBox())!;
    for (const selector of [`${ASIDE} [data-scroll-area-viewport]`, `${DESIGN_SCROLL} [data-scroll-area-viewport]`]) {
      const viewport = page.locator(selector);
      for (const position of [0, 160, Infinity]) {
        await viewport.evaluate((el, position) => { el.scrollTop = Number.isFinite(position) ? position : el.scrollHeight; }, position);
        const bounds = (await viewport.boundingBox())!;
        expect(Math.abs(bounds.y - (nav.y + nav.height))).toBeLessThanOrEqual(1);
        expect(Math.abs(bounds.y + bounds.height - footer.y)).toBeLessThanOrEqual(1);
      }
    }
    await page.screenshot({ path: testInfo.outputPath("design-scroll-bottom.png") });
    await page.locator(`${ASIDE} [data-scroll-area-viewport]`).evaluate((el) => { el.scrollTop = 100; });
    await page.locator(`${DESIGN_SCROLL} [data-scroll-area-viewport]`).evaluate((el) => { el.scrollTop = 160; });
    await page.screenshot({ path: testInfo.outputPath("design-scroll-middle.png") });
  });

  test("simulation keeps equal side insets and a full-height scroll viewport", async ({ page }, testInfo) => {
    await gotoDesignApp(page);
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    const viewport = page.locator("#simulation-scroll [data-scroll-area-viewport]");
    const nav = (await page.getByRole("navigation", { name: "Design workflows" }).boundingBox())!;
    const footer = (await page.locator("footer").boundingBox())!;
    const diagrams = (await page.getByRole("region", { name: "Simulation diagrams" }).boundingBox())!;
    const settings = (await page.locator("#panel-simulate aside").boundingBox())!;
    const width = page.viewportSize()!.width;
    expect(diagrams.x).toBe(16);
    expect(Math.abs(width - settings.x - settings.width - 16)).toBeLessThanOrEqual(1);
    for (const position of [0, 160, Infinity]) {
      await viewport.evaluate((el, position) => { el.scrollTop = Number.isFinite(position) ? position : el.scrollHeight; }, position);
      const bounds = (await viewport.boundingBox())!;
      expect(bounds.x).toBe(0);
      expect(Math.abs(bounds.width - width)).toBeLessThanOrEqual(1);
      expect(Math.abs(bounds.y - (nav.y + nav.height))).toBeLessThanOrEqual(1);
      expect(Math.abs(bounds.y + bounds.height - footer.y)).toBeLessThanOrEqual(1);
    }
    await page.screenshot({ path: testInfo.outputPath("simulation-scroll-bottom.png") });
    await viewport.evaluate((el) => { el.scrollTop = 0; });
    await page.screenshot({ path: testInfo.outputPath("simulation-insets.png") });
  });

  test("sensor settings fill the space between the dividers", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await page.goto("/");
    await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
    await page.getByRole("dialog", { name: "New coil file", exact: true }).getByRole("button", { name: /^Sensor coil/ }).click();
    const viewport = page.locator("#sensor-settings-scroll [data-scroll-area-viewport]");
    const nav = (await page.getByRole("navigation", { name: "Design workflows" }).boundingBox())!;
    const footer = (await page.locator("footer").boundingBox())!;
    await expect(viewport).toBeVisible();
    expect(await viewport.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    for (const position of [0, 160, Infinity]) {
      await viewport.evaluate((el, position) => { el.scrollTop = Number.isFinite(position) ? position : el.scrollHeight; }, position);
      const bounds = (await viewport.boundingBox())!;
      expect(Math.abs(bounds.y - (nav.y + nav.height))).toBeLessThanOrEqual(1);
      expect(Math.abs(bounds.y + bounds.height - footer.y)).toBeLessThanOrEqual(1);
    }
  });

  test("switching workflow tabs preserves each scroll position", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await gotoDesignApp(page);
    const design = page.locator(`${DESIGN_SCROLL} [data-scroll-area-viewport]`);
    await design.evaluate((el) => { el.scrollTop = 160; });
    const designPosition = await design.evaluate((el) => el.scrollTop);
    expect(designPosition).toBeGreaterThan(0);
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    const simulation = page.locator("#simulation-scroll [data-scroll-area-viewport]");
    await simulation.evaluate((el) => { el.scrollTop = 200; });
    const simulationPosition = await simulation.evaluate((el) => el.scrollTop);
    expect(simulationPosition).toBeGreaterThan(0);
    await page.getByRole("tab", { name: /^Design/i }).click();
    await expect.poll(() => design.evaluate((el) => el.scrollTop)).toBe(designPosition);
    await page.getByRole("tab", { name: /^Simulate/i }).click();
    await expect.poll(() => simulation.evaluate((el) => el.scrollTop)).toBe(simulationPosition);
  });

  test("scrollbar thumbs reach both ends without leaving their tracks", async ({ page }) => {
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 600 });
    await gotoDesignApp(page);
    for (const selector of [DESIGN_SCROLL, `${ASIDE} [data-scroll-area-root]`]) {
      const root = page.locator(selector);
      const viewport = root.locator("[data-scroll-area-viewport]");
      const track = root.locator("[data-scroll-area-scrollbar]");
      const thumb = track.locator("[data-scroll-area-thumb]");
      if (await viewport.evaluate((el) => el.scrollHeight <= el.clientHeight)) continue;
      await root.hover();
      await expect(track).toBeVisible();
      await expect(thumb).toBeVisible();
      expect(await viewport.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
      await viewport.evaluate((el) => { el.scrollTop = 0; });
      await expect.poll(async () => {
        const bar = (await track.boundingBox())!;
        const handle = (await thumb.boundingBox())!;
        return Math.abs(handle.y - (bar.y + 2));
      }).toBeLessThanOrEqual(1);
      await viewport.evaluate((el) => { el.scrollTop = el.scrollHeight; });
      await expect.poll(async () => {
        const bar = (await track.boundingBox())!;
        const handle = (await thumb.boundingBox())!;
        return Math.abs(handle.y + handle.height - (bar.y + bar.height - 2));
      }).toBeLessThanOrEqual(1);
    }
  });

  test("left column first card aligns with the right column content padding", async ({
    page,
  }) => {
    await gotoDesignApp(page);
    const panel = await box(page, designPanel(page));
    const card = await box(page, leftColumnFirstCard(page));
    expect(panel).not.toBeNull();
    expect(card).not.toBeNull();
    // The right column's content begins 16px (p-4) below the panel edge;
    // the aside must start at exactly the same visual line.
    expect(Math.abs(card!.y - (panel!.y + 16))).toBeLessThanOrEqual(1);
  }, { tag: ["@visual", "@desktop"] });

  test("design-tab scrollbar sits flush with the right window edge", async ({
    page,
  }) => {
    await gotoDesignApp(page);
    // The ScrollArea ROOT carries the geometry (kata 2npg): it must extend
    // to the window's right edge, while the actual scrolling element is its
    // Bits viewport descendant.
    const scroll = page.locator(DESIGN_SCROLL);
    await expect(scroll).toBeVisible();
    const viewport = scroll.locator("[data-scroll-area-viewport]");
    await expect(viewport).toHaveCSS("overflow-y", "scroll");
    const b = await box(page, scroll);
    expect(b).not.toBeNull();
    const innerWidth = await page.evaluate(() => window.innerWidth);
    // The scrolling container must extend to the window's right edge so the
    // scrollbar no longer floats 16-32px inside the layout.
    expect(innerWidth - (b!.x + b!.w)).toBeLessThanOrEqual(1);
  }, { tag: ["@visual", "@desktop"] });

  test("traces preview is visible in the Design-tab left column", async ({
    page,
  }) => {
    await gotoDesignApp(page);
    const aside = page.locator(ASIDE);
    const coilHeading = aside.locator("text=Coil Preview");
    await expect(coilHeading).toBeVisible();
    // It renders the canvas viewer, not a blank "awaiting generation" state.
    const preview = aside.locator("[aria-label='Coil preview']");
    await expect(preview).toBeVisible();
    await expect(
      preview.locator("canvas[data-revision]"),
    ).toBeVisible();
  }, { tag: ["@visual", "@desktop"] });

  test("page height is locked and the footer is always visible", async ({
    page,
  }) => {
    await gotoDesignApp(page);
    // Attempt to scroll the window: it must not move (the root scroller is
    // locked at the desktop layout; only the inner columns scroll).
    await page.evaluate(() => window.scrollTo(0, 400));
    await page.waitForTimeout(150);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);

    const footer = page.locator("footer");
    await expect(footer).toBeVisible();
    const fb = await footer.boundingBox();
    expect(fb).not.toBeNull();
    expect(fb!.y).toBeGreaterThanOrEqual(0);
    const innerHeight = await page.evaluate(() => window.innerHeight);
    expect(fb!.y + fb!.height).toBeLessThanOrEqual(innerHeight + 1);
  }, { tag: ["@visual", "@desktop"] });

  test("left and right columns scroll independently", async ({ page }) => {
    await gotoDesignApp(page);
    // Both columns are Bits UI ScrollAreas at the lg layout (kata 2npg):
    // the aside and the settings root are the positioned containers, the
    // real scrollers are their viewport descendants.
    const aside = page.locator(ASIDE);
    const right = page.locator(DESIGN_SCROLL);
    const leftViewport = aside.locator("[data-scroll-area-viewport]");
    const rightViewport = right.locator("[data-scroll-area-viewport]");
    await expect(leftViewport).toHaveCSS("overflow-y", "scroll");
    await expect(rightViewport).toHaveCSS("overflow-y", "scroll");

    const overflow = await page.evaluate(() => {
      const left = document.querySelector(
        "aside[aria-label='Coil preview panel'] [data-scroll-area-viewport]",
      )!;
      const settings = document.querySelector(
        "#design-settings-scroll [data-scroll-area-viewport]",
      )!;
      return {
        left: left.scrollHeight > left.clientHeight,
        settings: settings.scrollHeight > settings.clientHeight,
      };
    });
    // The simplified Design tab can fit completely at the wide viewport. In
    // that case there is no scroll position to assert; the desktop-tauri
    // viewport still exercises the independent-scroll behavior below.
    test.skip(
      !overflow.left || !overflow.settings,
      "this viewport has no overflowing design column",
    );

    // Scrolling inside the left column must not move the right column.
    await leftViewport.evaluate((el) => {
      el.scrollTop = 200;
    });
    await page.waitForTimeout(120);
    const afterLeft = await page.evaluate(() => ({
      left: document.querySelector("aside[aria-label='Coil preview panel'] [data-scroll-area-viewport]")!.scrollTop,
      right: document.querySelector("#design-settings-scroll [data-scroll-area-viewport]")!.scrollTop,
      windowY: window.scrollY,
    }));
    expect(afterLeft.left).toBeGreaterThan(0);
    expect(afterLeft.right).toBe(0);
    expect(afterLeft.windowY).toBe(0);

    // And scrolling the right column must not move the left column.
    await rightViewport.evaluate((el) => {
      el.scrollTop = 200;
    });
    await page.waitForTimeout(120);
    const afterRight = await page.evaluate(() => ({
      left: document.querySelector("aside[aria-label='Coil preview panel'] [data-scroll-area-viewport]")!.scrollTop,
      right: document.querySelector("#design-settings-scroll [data-scroll-area-viewport]")!.scrollTop,
    }));
    expect(afterRight.right).toBeGreaterThan(0);
    expect(afterRight.left).toBe(afterLeft.left);
  }, { tag: ["@visual", "@desktop"] });
});
