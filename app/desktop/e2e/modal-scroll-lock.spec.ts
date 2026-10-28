import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp, coilWorkspace } from "./helpers";

// ui-cleanup removed the coil-preview modal/backdrop entirely. Keep actual
// modal scroll containment covered with the still-supported Add driver dialog,
// rather than restoring the retired preview solely to exercise its old guard.
async function openModal(page: Page) {
  await gotoDesignApp(page);
  const workspace = coilWorkspace(page);
  await workspace.getByRole("button", { name: "Driver settings", exact: true }).click();
  await expect(page.locator("#design-settings-scroll")).toHaveCount(0);
  await page.getByRole("button", { name: "Add driver…", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Add driver", exact: true });
  await expect(modal.getByLabel("Driver name")).toBeFocused();
  return modal;
}

async function scrollState(page: Page) {
  return page.evaluate(() => ({
    document: document.scrollingElement?.scrollTop ?? -1,
    settings: document.querySelector("#design-settings-scroll [data-scroll-area-viewport]")?.scrollTop ?? -1,
    workspace: document.querySelector('[aria-label="Coil design workspace"]')?.getBoundingClientRect().y,
  }));
}

async function wheel(page: Page, x: number, y: number, delta: number) {
  await page.evaluate(() => {
    (window as any).__scrollTestWheels = 0;
    window.addEventListener("wheel", () => (window as any).__scrollTestWheels++, { once: true });
  });
  await page.mouse.move(x, y);
  await page.mouse.wheel(0, delta);
  await expect.poll(() => page.evaluate(() => (window as any).__scrollTestWheels)).toBe(1);
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

test.describe("active modal scroll containment", () => {
  test("backdrop wheel does not move the background and Escape restores focus", async ({ page }) => {
    const modal = await openModal(page);
    const before = await scrollState(page);
    await wheel(page, 4, 400, 480);
    expect(await scrollState(page)).toEqual(before);
    await expect(modal).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Add driver…", exact: true })).toBeFocused();
    await expect(coilWorkspace(page)).toBeVisible();
  });

  test("a short modal scrolls its own content without chaining to the workspace", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 480 });
    const modal = await openModal(page);
    const before = await scrollState(page);
    await expect.poll(() => modal.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    const box = (await modal.boundingBox())!;
    await wheel(page, box.x + box.width - 10, box.y + box.height / 2, 600);
    await expect.poll(() => modal.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    expect(await scrollState(page)).toEqual(before);
    await modal.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(modal).toHaveCount(0);
  });

  test("phone backdrop stays fixed and closing does not leave a temporary lock", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await gotoDesignApp(page);
    const overflow = () => page.evaluate(() => ({ root: document.documentElement.style.overflow, body: document.body.style.overflow }));
    const baseline = await overflow();
    await coilWorkspace(page).getByRole("button", { name: "Driver settings", exact: true }).click();
    await expect(page.locator("#design-settings-scroll")).toHaveCount(0);
    await page.getByRole("button", { name: "Add driver…", exact: true }).click();
    const modal = page.getByRole("dialog", { name: "Add driver", exact: true });
    await expect(modal.getByLabel("Driver name")).toBeFocused();
    const before = await scrollState(page);
    await wheel(page, 4, 350, 500);
    expect(await scrollState(page)).toEqual(before);
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    await expect.poll(overflow).toEqual(baseline);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
