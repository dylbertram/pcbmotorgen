import { test, expect } from "@playwright/test";
import { gotoDesignApp, openCoilPreview } from "./helpers";

for (const simulate of [false, true]) for (const mobile of [false, true]) {
  test(`position and layers work in every viewport ${simulate ? "simulate" : "design"} ${mobile ? "mobile" : "desktop"}`, async ({ page }, info) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await gotoDesignApp(page);
    if (simulate) await page.getByRole("tab", { name: /^Simulate/i }).click();
    await openCoilPreview(page);
    const workspace = page.getByRole("region", { name: "Coil design workspace", exact: true });
    const modes = workspace.getByRole("group", { name: "Position bar mode", exact: true });
    let position: string | null = null;
    for (const [label, id] of [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]]) {
      await workspace.getByRole("button", { name: label, exact: true }).click();
      const viewer = workspace.getByTestId(`coil-${id}`);
      await expect(viewer).toHaveAttribute("data-camera", /position/);
      await expect(modes).toBeVisible();
      await modes.getByRole("button", { name: "position", exact: true }).click();
      const slider = workspace.getByRole("slider", { name: "Mover position slider (mm)", exact: true });
      await expect(slider).toBeVisible();
      if (position !== null) await expect(slider).toHaveAttribute("aria-valuenow", position);
      await slider.focus(); await page.keyboard.press(id === "top" ? "Home" : "ArrowRight");
      position = await slider.getAttribute("aria-valuenow");
      await expect(workspace.getByRole("spinbutton", { name: "Mover position (mm)", exact: true })).toHaveValue(position!);
      await modes.getByRole("button", { name: "layers", exact: true }).click();
      const layers = workspace.getByRole("slider", { name: "Preview layer", exact: true });
      await expect(layers).toBeVisible();
      await layers.fill("1");
      await expect(viewer).toHaveAttribute("data-layers", "1");
      await expect(layers).toHaveAttribute("aria-valuetext", "Layer 1");
      await layers.fill("0");
      await expect.poll(async () => Number(await viewer.getAttribute("data-layers"))).toBeGreaterThan(1);
      const frame = (await workspace.getByRole("img", { name: "Coil preview", exact: true }).boundingBox())!;
      const box = (await modes.locator("..").boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(frame.x);
      expect(box.x + box.width).toBeLessThanOrEqual(frame.x + frame.width + 1);
      expect(box.y + box.height).toBeLessThanOrEqual(frame.y + frame.height);
    }
    await page.screenshot({ path: info.outputPath("all-view-scrubber.png") });
  });
}
