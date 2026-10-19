import { expect, type Locator, type Page } from "@playwright/test";

/** The Design tab's scrollable settings container. */
export const DESIGN_SCROLL = "#design-settings-scroll";

/** The embedded motor workspace, retained as ASIDE for shared preview tests. */
export const ASIDE = "#panel-design";

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

/** The full Design tab's outer box. */
export function designPanel(page: Page) {
  return page.locator("#panel-design");
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

/** The constraints section in the preview's Design settings drawer. */
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
