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

test("a renderer-module load failure also enables the top-down copper fallback",async({page})=>{
  await page.addInitScript(()=>{
    const stroke=CanvasRenderingContext2D.prototype.stroke;
    CanvasRenderingContext2D.prototype.stroke=function(...args:[Path2D?]){
      if(this.strokeStyle==="#10b981")this.canvas.dataset.fallbackCopper="drawn";
      if(args[0])stroke.call(this,args[0]);else stroke.call(this);
    };
  });
  await page.route(/\/CoilPreview3DView\.svelte(?:\?.*)?$/,route=>route.abort());
  await gotoDesignApp(page);
  const workspace=page.getByRole("region",{name:"Coil design workspace",exact:true});
  await expect(workspace.getByRole("status").filter({hasText:"Top-down uses the 2D fallback"})).toBeVisible();
  await expect.poll(async()=>Number(await workspace.getByTestId("coil-annotations").getAttribute("data-segments"))).toBeGreaterThan(0);
  // Unlike normal annotation-only mode, fallback renders the physical copper.
  await expect(workspace.getByTestId("coil-annotations")).toHaveAttribute("data-fallback-copper","drawn");
});
