import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test.beforeEach(async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      export async function bindProjectMenuActions(handlers) {
        const handle = event => handlers[event.detail]?.();
        window.addEventListener('test-file-action', handle);
        return () => window.removeEventListener('test-file-action', handle);
      }`,
  }));
  await page.route("**/src/lib/files.ts", route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function saveTextToFile() {
      if (window.__exportError) throw new Error('Folder is not writable');
      return window.__exportPath ?? '/exports/coils.dxf';
    }`,
  }));
  await gotoDesignApp(page);
  await page.mouse.move(0, 0);
  await page.clock.install();
});

async function exportDxf(page: Page) {
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "exportDxf" })));
}

test("temporary notifications float without shifting content and expire", async ({ page }) => {
  const before = await page.locator("#tab-design").boundingBox();
  await exportDxf(page);
  const notification = page.getByRole("status", { name: "Project notification" });
  await expect(notification).toContainText("Exported DXF to /exports/coils.dxf.");
  await expect(notification).toHaveCSS("position", "fixed");
  expect(await page.locator("#tab-design").boundingBox()).toEqual(before);
  await page.clock.runFor(3999);
  await expect(notification).toBeVisible();
  await page.clock.runFor(1);
  await expect(notification).toHaveCount(0);
});

test("hover and keyboard focus pause timeout, replacement resets it, dismissal is optional", async ({ page }) => {
  await exportDxf(page);
  const notification = page.getByRole("status", { name: "Project notification" });
  await expect(notification).toBeVisible();
  await notification.hover();
  await page.clock.runFor(5000);
  await expect(notification).toBeVisible();
  await page.mouse.move(0, 0);
  await notification.getByRole("button", { name: "Dismiss notification" }).focus();
  await page.clock.runFor(5000);
  await expect(notification).toBeVisible();
  await page.locator("#tab-design").focus();
  await page.clock.runFor(3000);
  await page.evaluate(() => (window as any).__exportPath = "/exports/another.dxf");
  await exportDxf(page);
  await expect(notification).toContainText("another.dxf");
  await page.clock.runFor(3000);
  await expect(notification).toBeVisible();
  await notification.getByRole("button", { name: "Dismiss notification" }).click();
  await expect(notification).toHaveCount(0);
  await page.clock.runFor(5000);
  await expect(notification).toHaveCount(0);
});

test("errors remain visible rather than timing out", async ({ page }) => {
  await page.evaluate(() => (window as any).__exportError = true);
  await exportDxf(page);
  await expect(page.getByText("DXF export failed: Folder is not writable")).toBeVisible();
  await page.clock.runFor(10000);
  await expect(page.getByText("DXF export failed: Folder is not writable")).toBeVisible();
  await expect(page.getByRole("status", { name: "Project notification" })).toHaveCount(0);
});
