import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("3D reports unavailable WebGL and can return to top-down", async ({ page }) => {
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      if (type === "webgl" || type === "webgl2" || type === "experimental-webgl") return null;
      return getContext.call(this, type, ...args);
    } as typeof getContext;
  });
  await gotoDesignApp(page);
  const dialog = page.getByRole("region", { name: "Coil design workspace", exact: true });
  await dialog.getByRole("button", { name: "Display", exact: true }).click();
  const display = page.getByRole("dialog", { name: "Coil preview display", exact: true });
  await display.getByRole("radio", { name: "3D", exact: true }).check();
  await expect(dialog.getByRole("status").filter({ hasText: "3D rendering is unavailable" })).toBeVisible();
  await display.getByRole("radio", { name: "Top-down", exact: true }).check();
  await expect(dialog.locator("canvas")).toBeVisible();
  await expect(dialog.getByTestId("coil-iso")).toHaveCount(0);
});
