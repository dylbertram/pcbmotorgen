import { test, expect, type Page } from "@playwright/test";
import { ASIDE, gotoDesignApp } from "./helpers";

/**
 * Modal scroll-lock regression suite (Kata xy31).
 *
 * Ticket: with the coil preview lightbox open, hovering the background
 * design preview (stack-diagram area) and wheel-scrolling leaked scroll
 * into the page behind the modal. Expected: an open modal blocks background
 * scroll ENTIRELY — wheel events on the backdrop must be defaultPrevented,
 * nothing behind the modal may move (lg: the left reflection column;
 * below-lg: the document itself), and the lock must RELEASE on close so the
 * background scrolls normally again.
 *
 * Wheel points deliberately sit INSIDE the 16px backdrop margin (x < 16),
 * which is always the dimmed backdrop itself — never the centered panel.
 * These tests drive REAL wheel input (Playwright's mouse.wheel dispatches
 * trusted CDP wheel events), so the non-passive backdrop guard and the
 * document overflow lock are exercised exactly as a user's trackpad would.
 */

/** The coil preview lightbox dialog (open via the ⤢ button). */
const EXPAND_BUTTON = "button[aria-label='Expand coil preview']";
const LIGHTBOX = "[role='dialog'][aria-label='Coil Preview — expanded']";

/**
 * The modal's own scrollable panel. Since kata 2npg the lightbox is a Bits
 * UI Dialog and the dialog CONTENT itself is the scrolling panel (Bits
 * renders no intermediate panel wrapper anymore).
 */
const LIGHTBOX_PANEL = LIGHTBOX;

/** Let one compositor frame pass so any (illegal) scroll becomes visible. */
async function settleScroll(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await page.waitForTimeout(30);
}

/** Record whether the next wheel events arrive at window-level prevented. */
async function watchWheelPrevented(page: Page) {
  await page.evaluate(() => {
    (window as { __wheelWasPrevented?: boolean }).__wheelWasPrevented = false;
    window.addEventListener("wheel", (e) => {
      (window as { __wheelWasPrevented?: boolean }).__wheelWasPrevented =
        e.defaultPrevented;
    });
  });
}

async function wheelWasPrevented(page: Page): Promise<boolean> {
  return page.evaluate(
    () => (window as { __wheelWasPrevented?: boolean }).__wheelWasPrevented,
  );
}

async function openLightbox(page: Page) {
  await gotoDesignApp(page);
  await page.locator(EXPAND_BUTTON).click();
  await expect(page.locator(LIGHTBOX)).toBeVisible();
}

test.describe("coil preview modal scroll lock @interaction @desktop", () => {
  test("lg: wheel on the backdrop is prevented and the background never moves", async ({
    page,
  }) => {
    await openLightbox(page);

    // The document overflow lock must be applied while the modal is open.
    const inlineOverflow = await page.evaluate(() => ({
      root: document.documentElement.style.overflow,
      body: document.body.style.overflow,
    }));
    expect(inlineOverflow).toEqual({ root: "hidden", body: "hidden" });

    const before = await page.evaluate(() => ({
      aside: document.querySelector("aside")?.scrollTop ?? -1,
      document: document.scrollingElement?.scrollTop ?? -1,
    }));

    // Trusted wheel over the dimmed backdrop (x=4 → inside the 16px margin,
    // guaranteed NOT the panel). Without the fix this is not prevented.
    await watchWheelPrevented(page);
    await page.mouse.move(4, 400);
    await page.mouse.wheel(0, 480);
    await settleScroll(page);

    expect(await wheelWasPrevented(page)).toBe(true);

    const after = await page.evaluate(() => ({
      aside: document.querySelector("aside")?.scrollTop ?? -1,
      document: document.scrollingElement?.scrollTop ?? -1,
    }));
    expect(after).toEqual(before);

    // Closing releases the inline lock.
    await page.keyboard.press("Escape");
    await expect(page.locator(LIGHTBOX)).toBeHidden();
    const released = await page.evaluate(() => ({
      root: document.documentElement.style.overflow,
      body: document.body.style.overflow,
    }));
    expect(released).toEqual({ root: "", body: "" });
  });

  test("lg: the modal panel still scrolls itself but never chains to the background", async ({
    page,
  }) => {
    // Short viewport guarantees the panel content overflows, so the
    // positive control (panel scrollTop moves) is never vacuous.
    await page.setViewportSize({ width: 1280, height: 560 });
    await openLightbox(page);

    const panel = page.locator(LIGHTBOX_PANEL);
    const panelBox = await panel.boundingBox();
    expect(panelBox).not.toBeNull();

    const overflows = await panel.evaluate(
      (el) => el.scrollHeight > el.clientHeight,
    );
    expect(overflows).toBe(true);

    // Baseline taken AFTER the modal is open: Playwright's click on the
    // expand button may have auto-scrolled the aside beforehand, so the
    // invariant is "the background does not move while the modal is open",
    // not "the background sits at scrollTop 0".
    const asideBefore = await page.evaluate(
      () => document.querySelector("aside")?.scrollTop ?? -1,
    );

    // Wheel inside the panel over its header row (not the canvas gesture
    // surface): the panel scrolls itself…
    await page.mouse.move(panelBox!.x + panelBox!.width / 2, panelBox!.y + 12);
    await page.mouse.wheel(0, 600);
    await settleScroll(page);

    const panelScrolled = await panel.evaluate((el) => el.scrollTop);
    expect(panelScrolled).toBeGreaterThan(0);

    // …and the reflection column behind the modal never moved.
    const asideScroll = await page.evaluate(
      () => document.querySelector("aside")?.scrollTop ?? -1,
    );
    expect(asideScroll).toBe(asideBefore);
  });

  test("below-lg: wheel on the backdrop is prevented, document never scrolls, and closing restores scrolling", async ({
    page,
  }) => {
    // Narrow viewport: columns stack and the PAGE is the background scroller.
    await page.setViewportSize({ width: 900, height: 700 });
    await openLightbox(page);

    // The background document must actually be scrollable here, or the
    // assertions below would pass vacuously.
    const scrollable = await page.evaluate(() => {
      const el = document.scrollingElement;
      return el ? el.scrollHeight > el.clientHeight : false;
    });
    expect(scrollable).toBe(true);

    const before = await page.evaluate(
      () => document.scrollingElement?.scrollTop ?? -1,
    );

    // Trusted wheel over the dimmed backdrop (x=4 → outside the panel).
    await watchWheelPrevented(page);
    await page.mouse.move(4, 350);
    await page.mouse.wheel(0, 500);
    await settleScroll(page);

    expect(await wheelWasPrevented(page)).toBe(true);
    const after = await page.evaluate(
      () => document.scrollingElement?.scrollTop ?? -1,
    );
    expect(after).toBe(before);

    // Close: lock releases and the background scrolls normally again
    // (catches a stuck overflow:hidden).
    await page.keyboard.press("Escape");
    await expect(page.locator(LIGHTBOX)).toBeHidden();
    const inlineOverflow = await page.evaluate(() => ({
      root: document.documentElement.style.overflow,
      body: document.body.style.overflow,
    }));
    expect(inlineOverflow).toEqual({ root: "", body: "" });

    await page.mouse.move(4, 350);
    await page.mouse.wheel(0, 400);
    await settleScroll(page);

    const unlocked = await page.evaluate(
      () => document.scrollingElement?.scrollTop ?? -1,
    );
    expect(unlocked).toBeGreaterThan(0);
  });
});
