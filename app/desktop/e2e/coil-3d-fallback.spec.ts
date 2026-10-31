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
  await dialog.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await expect(dialog.getByRole("status").filter({ hasText: "3D rendering is unavailable" })).toBeVisible();
  await dialog.getByRole("button", { name: "Top-down", exact: true }).click();
  await expect(dialog.locator("canvas")).toBeVisible();
  await expect(dialog.getByTestId("coil-iso")).toHaveCount(0);
});
