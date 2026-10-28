import { expect, test } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel } from "./helpers";

test.beforeEach(async ({ page }) => {
  // The browser has no native menu. Replace only the menu-event transport,
  // leaving the real App handlers and export/DRC components under test.
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace(
      "export async function bindProjectMenuActions(handlers) {",
      `export async function bindProjectMenuActions(handlers) {
        const handle = event => handlers[event.detail]?.();
        window.addEventListener('test-file-action', handle);
        return () => window.removeEventListener('test-file-action', handle);
      `,
    );
    await route.fulfill({ response, body });
  });
});

test("Export tab is removed and DRC is available beside Ready", async ({ page }) => {
  await gotoDesignApp(page);
  await expect(page.getByRole("tab", { name: "Export" })).toHaveCount(0);
  const trigger = page.getByRole("button", { name: /Design rule check:/ });
  await expect(trigger).toBeVisible();
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Design rule check", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Check layout" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("Send to KiCad opens details without leaving the Design tab", async ({ page }) => {
  await gotoDesignApp(page);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "sendKicad" })));
  const dialog = page.getByRole("dialog", { name: "Send to KiCad", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Connect" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Design" })).toHaveAttribute("aria-selected", "true");
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).toBeHidden();
});

test("DXF exports directly and New adds a file without clearing an edited design", async ({ page }) => {
  await page.route("**/src/lib/files.ts", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export async function saveTextToFile(content, fileName, extensions) {
      window.__savedDxf = { content, fileName, extensions };
      return '/exports/' + fileName;
    }`,
  }));
  await gotoDesignApp(page);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "exportDxf" })));
  await expect(page.getByText("Exported DXF to /exports/motor-coil.dxf.")).toBeVisible();
  const saved = await page.evaluate(() => (window as unknown as { __savedDxf: { content: string; fileName: string; extensions: string[] } }).__savedDxf);
  expect(saved.fileName).toBe("motor-coil.dxf");
  expect(saved.extensions).toEqual(["dxf"]);
  expect(saved.content).toContain("SECTION");
  await selectDesignPanel(page, "Magnets");
  await page.locator("input#magnet-count").fill("6");
  await page.locator("input#magnet-count").press("Enter");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "newFile" })));
  await page.getByRole("dialog", { name: "New coil file" }).getByRole("button", { name: /^Motor coil/ }).click();
  await selectDesignPanel(page, "Magnets");
  await expect(page.locator("input#magnet-count")).toHaveValue("12");
  await page.getByRole("tab", { name: /^M Untitled motor 1/ }).click();
  await selectDesignPanel(page, "Magnets");
  await expect(page.locator("input#magnet-count")).toHaveValue("6");
});
