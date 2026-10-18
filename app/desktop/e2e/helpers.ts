import { expect, type Locator, type Page } from "@playwright/test";

/** The Design tab's scrollable settings container. */
export const DESIGN_SCROLL = "#design-settings-scroll";

/** The persistent left column (aside) of the main grid. */
export const ASIDE = "aside[aria-label='Coil preview panel']";

/** Open a motor document with generated defaults in the workspace. */
export async function gotoDesignApp(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "New coil file", exact: true });
  await dialog.getByRole("button", { name: /^Motor coil/ }).click();
  await expect(dialog).toBeHidden();
}

/**
 * Geometry of an element relative to the viewport, as integers.
 * Returns null when the element is hidden/not attached.
 */
export async function box(page: Page, locator: Locator) {
  const b = await locator.boundingBox();
  if (!b) return null;
  return { x: b.x, y: b.y, w: b.width, h: b.height };
}

/** The Design panel's outer box (includes its p-4 padding). */
export function designPanel(page: Page) {
  return page.locator("#panel-design");
}

/**
 * The coil preview card in the left column's scroll area.
 */
export function leftColumnFirstCard(page: Page) {
  return page.locator(
    `${ASIDE} [data-scroll-area-content] > :first-child`,
  );
}

/** Active-area length readout in Design constraints. */
export function activeLengthReadout(page: Page) {
  return page.locator(
    `section[aria-labelledby="design-constraints-heading"] dt:has(> span:text-is("Active copper region")) + dd`,
  );
}

/** The "PCB trace total (X)" live output (traces' first-to-last X span). */
export function traceTotalReadout(page: Page) {
  return page.locator(
    `section[aria-labelledby="design-constraints-heading"] dt:has(> span:text-is("PCB trace total (X)")) + dd`,
  );
}

/** The Design constraints box (right column, top of the Design settings). */
export function designConstraintsPanel(page: Page) {
  return page.locator(
    `section[aria-labelledby="design-constraints-heading"]`,
  );
}

/** NumberField wrapper by aria-label. */
export function numberField(page: Page, ariaLabel: string) {
  return page.locator(`input[aria-label="${ariaLabel}"]`);
}

/** Traffic-light: helper that retries an async expectation until it passes. */
export function eventually(
  assertion: () => Promise<void>,
  timeoutMs = 4000,
): Promise<void> {
  return expect(async () => {
    await assertion();
  }).toPass({ timeout: timeoutMs });
}
